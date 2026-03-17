from flask_cors import CORS
from flask import Flask, request, jsonify
from functools import wraps
import jwt
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import yfinance as yf

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
        # Busca TODOS os aportes do usuário
        response = supabase.table('investments').select('*').eq('user_id', current_user_id).execute()
        investments = response.data

        # 1. Agrupar ativos com o mesmo nome/ticker
        grouped_assets = {}
        for asset in investments:
            ticker = asset['ticker_or_name']
            qty = float(asset['quantity'])
            avg_price_buy = float(asset['average_price'])
            # Se não tiver preço atual salvo, usa o preço de compra
            curr_price = float(asset['current_price']) if asset['current_price'] else avg_price_buy
            invested_value = qty * avg_price_buy

            if ticker not in grouped_assets:
                grouped_assets[ticker] = {
                    "class": asset['asset_class'],
                    "total_quantity": qty,
                    "total_invested": invested_value,
                    "current_price": curr_price,
                    "metadata": asset.get('metadata')
                }
            else:
                grouped_assets[ticker]['total_quantity'] += qty
                grouped_assets[ticker]['total_invested'] += invested_value
                # Assume a cotação atualizada mais recente que encontrar nos registros
                if asset['current_price']:
                    grouped_assets[ticker]['current_price'] = curr_price

        # 2. Calcular rentabilidade da posição agrupada
        processed_assets = []
        total_invested_all = 0
        current_total_value = 0
        distribution = {}

        for ticker, data in grouped_assets.items():
            # Cálculo matemático do Preço Médio
            avg_price_calculated = data['total_invested'] / data['total_quantity'] if data['total_quantity'] > 0 else 0
            
            # Ajuste de quantidade para Gado (descontando mortalidade)
            adjusted_quantity = data['total_quantity']
            if data['class'] == 'CATTLE' and data.get('metadata'):
                mortality_rate = float(data['metadata'].get('mortality_rate', 0))
                adjusted_quantity = data['total_quantity'] * (1 - mortality_rate)

            # Valorização Atual
            current_value = adjusted_quantity * data['current_price']
            
            profitability = 0
            if data['total_invested'] > 0:
                profitability = ((current_value - data['total_invested']) / data['total_invested']) * 100

            total_invested_all += data['total_invested']
            current_total_value += current_value

            asset_class = data['class']
            distribution[asset_class] = distribution.get(asset_class, 0) + current_value

            processed_assets.append({
                "ticker": ticker,
                "name": ticker,
                "class": data['class'],
                "quantity": round(data['total_quantity'], 4),
                "average_price": round(avg_price_calculated, 2),
                "current_price": round(data['current_price'], 2),
                "current_value": round(current_value, 2),
                "profitability_percent": round(profitability, 2)
            })
            
        # Calcular porcentagens do Gráfico de Pizza
        for k, v in distribution.items():
            distribution[k] = round((v / current_total_value) * 100, 2) if current_total_value > 0 else 0

        return jsonify({
            "total_invested": round(total_invested_all, 2),
            "current_balance": round(current_total_value, 2),
            "portfolio_profitability": round(((current_total_value - total_invested_all) / total_invested_all * 100), 2) if total_invested_all > 0 else 0,
            "distribution": distribution,
            "assets": processed_assets
        }), 200

    except Exception as e:
        print(f"Erro no calculo: {str(e)}")
        return jsonify({'error': str(e)}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/investments/update-prices', methods=['POST'])
@token_required
def update_stock_prices(current_user_id):
    try:
        response = supabase.table('investments').select('*').eq('user_id', current_user_id).eq('asset_class', 'STOCKS').execute()
        investments = response.data

        updated_count = 0
        
        for inv in investments:
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

        return jsonify({
            "message": "Cotações atualizadas com sucesso", 
            "updated_count": updated_count
        }), 200

    except Exception as e:
        print(f"ERRO FATAL NA ROTA UPDATE-PRICES: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)