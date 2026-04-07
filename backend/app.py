from flask_cors import CORS
from flask import Flask, request, jsonify
from functools import wraps
import jwt
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import yfinance as yf
# --- NOVAS IMPORTAÇÕES PARA A RENDA FIXA ---
import json
import urllib.request
from datetime import datetime

load_dotenv()

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Middleware de Autenticação JWT
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or not token.startswith("Bearer "):
            print("❌ Backend: Nenhum token recebido do React.")
            return jsonify({'message': 'Token está faltando ou é inválido!'}), 401
        
        token = token.split(" ")[1]
        try:
            user_response = supabase.auth.get_user(token)
            current_user_id = user_response.user.id
            print(f"✅ Backend: Usuário {current_user_id} autenticado com sucesso!")
        except Exception as e:
            print(f"❌ Backend: Falha na autenticação -> {str(e)}")
            return jsonify({'message': 'Token inválido ou expirado!', 'error': str(e)}), 401
            
        return f(current_user_id, *args, **kwargs)
    return decorated

@app.route('/api/investments/portfolio', methods=['GET'])
@token_required
def get_portfolio(current_user_id):
    try:
        response = supabase.table('investments').select('*').eq('user_id', current_user_id).execute()
        investments = response.data

        # 1. Agrupar ativos
        grouped_assets = {}
        for asset in investments:
            ticker = asset['ticker_or_name']
            asset_class = asset['asset_class']
            qty = float(asset['quantity'])
            avg_price_buy = float(asset['average_price'])
            curr_price = float(asset['current_price']) if asset['current_price'] else avg_price_buy
            invested_value = qty * avg_price_buy

            group_key = str(asset['id']) if asset_class == 'FIXED_INCOME' else ticker

            if group_key not in grouped_assets:
                grouped_assets[group_key] = {
                    "id": group_key,
                    "original_ticker": ticker,
                    "class": asset_class,
                    "total_quantity": qty,
                    "total_invested": invested_value,
                    "current_price": curr_price,
                    "metadata": asset.get('metadata')
                }
            else:
                grouped_assets[group_key]['total_quantity'] += qty
                grouped_assets[group_key]['total_invested'] += invested_value
                if asset['current_price']:
                    grouped_assets[group_key]['current_price'] = curr_price

        # 2. Calcular rentabilidade e IMPOSTO DE RENDA
        processed_assets = []
        total_invested_all = 0
        current_total_value = 0
        current_net_value_all = 0
        distribution = {}

        for group_key, data in grouped_assets.items():
            avg_price_calculated = data['total_invested'] / data['total_quantity'] if data['total_quantity'] > 0 else 0
            
            adjusted_quantity = data['total_quantity']
            if data['class'] == 'CATTLE' and data.get('metadata'):
                mortality_rate = float(data['metadata'].get('mortality_rate', 0))
                adjusted_quantity = data['total_quantity'] * (1 - mortality_rate)

            current_value = adjusted_quantity * data['current_price']
            
            profitability = 0
            if data['total_invested'] > 0:
                profitability = ((current_value - data['total_invested']) / data['total_invested']) * 100

            # LÓGICA DE IMPOSTO DE RENDA
            net_value = current_value
            taxes = 0
            is_tax_free = False
            
            if data['class'] == 'FIXED_INCOME' and data.get('metadata'):
                meta = data['metadata']
                is_tax_free = meta.get('is_tax_free', False)
                purchase_date_str = meta.get('purchase_date')
                
                # O IR só incide sobre o LUCRO
                profit = current_value - data['total_invested']
                
                if profit > 0 and not is_tax_free and purchase_date_str:
                    purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d')
                    days_invested = (datetime.now() - purchase_date).days
                    
                    # Tabela Regressiva da Renda Fixa
                    if days_invested <= 180:
                        tax_rate = 0.225 # 22,5%
                    elif days_invested <= 360:
                        tax_rate = 0.200 # 20%
                    elif days_invested <= 720:
                        tax_rate = 0.175 # 17,5%
                    else:
                        tax_rate = 0.150 # 15%
                        
                    taxes = profit * tax_rate
                    net_value = current_value - taxes

            total_invested_all += data['total_invested']
            current_total_value += current_value
            current_net_value_all += net_value

            asset_class = data['class']
            distribution[asset_class] = distribution.get(asset_class, 0) + current_value

            processed_assets.append({
                "id": data["id"],
                "ticker": data["original_ticker"],
                "name": data["original_ticker"],
                "class": data['class'],
                "quantity": round(data['total_quantity'], 4),
                "average_price": round(avg_price_calculated, 2),
                "current_price": round(data['current_price'], 2),
                "current_value": round(current_value, 2),
                "net_value": round(net_value, 2),
                "taxes": round(taxes, 2),
                "is_tax_free": is_tax_free,
                "profitability_percent": round(profitability, 2)
            })
            
        for k, v in distribution.items():
            distribution[k] = round((v / current_total_value) * 100, 2) if current_total_value > 0 else 0

        return jsonify({
            "total_invested": round(total_invested_all, 2),
            "current_balance": round(current_total_value, 2),
            "current_net_balance": round(current_net_value_all, 2),
            "portfolio_profitability": round(((current_total_value - total_invested_all) / total_invested_all * 100), 2) if total_invested_all > 0 else 0,
            "distribution": distribution,
            "assets": processed_assets
        }), 200

    except Exception as e:
        print(f"Erro no calculo: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/investments/update-prices', methods=['POST'])
@token_required
def update_stock_prices(current_user_id):
    try:
        response = supabase.table('investments').select('*').eq('user_id', current_user_id).execute()
        investments = response.data

        updated_count = 0
        
        for inv in investments:
            # ATUALIZAÇÃO DE AÇÕES (YFINANCE)
            if inv['asset_class'] == 'STOCKS':
                ticker_symbol = inv['ticker_or_name'].strip().upper()
                yf_symbol = ticker_symbol

                if not yf_symbol.endswith('.SA') and any(char.isdigit() for char in yf_symbol):
                    yf_symbol = f"{yf_symbol}.SA"
                
                try:
                    ticker = yf.Ticker(yf_symbol)
                    current_price = ticker.fast_info['last_price']
                    
                    supabase.table('investments').update({
                        'current_price': round(current_price, 2)
                    }).eq('id', inv['id']).execute()
                    
                    updated_count += 1
                except Exception as e:
                    print(f"Erro ao buscar cotação para {yf_symbol}: {e}")
                    continue 
            
            # ATUALIZAÇÃO DE RENDA FIXA (CDI - BANCO CENTRAL)
            elif inv['asset_class'] == 'FIXED_INCOME':
                meta = inv.get('metadata')
                if meta and 'cdi_percentage' in meta:
                    cdi_pct = float(meta['cdi_percentage'])
                    
                    # Usa a data de aplicação
                    date_str = meta.get('purchase_date')
                    if date_str:
                        dt_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    else:
                        dt_obj = datetime.strptime(inv['created_at'][:10], '%Y-%m-%d')
                    
                    start_date_bcb = dt_obj.strftime('%d/%m/%Y')
                    end_date_bcb = datetime.now().strftime('%d/%m/%Y')
                    
                    # API do Banco Central (Série 12: Taxa de juros - CDI)
                    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={start_date_bcb}&dataFinal={end_date_bcb}"
                    
                    try:
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req) as response_bcb:
                            if response_bcb.status == 200:
                                cdi_data = json.loads(response_bcb.read().decode())
                                accumulated = 1.0
                                
                                # Acumula os juros compostos diários
                                for day in cdi_data:
                                    daily_rate = float(day['valor']) / 100
                                    # Rentabilidade diária multiplicada pela % do CDI contratada
                                    accumulated *= (1 + (daily_rate * cdi_pct))
                                
                                # O novo "preço" (valor total do título)
                                new_price = float(inv['average_price']) * accumulated
                                
                                supabase.table('investments').update({
                                    'current_price': round(new_price, 2)
                                }).eq('id', inv['id']).execute()
                                
                                updated_count += 1
                    except Exception as e:
                        print(f"Erro ao buscar CDI para {inv['ticker_or_name']}: {e}")

        return jsonify({
            "message": "Cotações e CDI atualizados com sucesso", 
            "updated_count": updated_count
        }), 200

    except Exception as e:
        print(f"ERRO FATAL NA ROTA UPDATE-PRICES: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)