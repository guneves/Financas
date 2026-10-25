package br.financas.app;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * O put do org.json sem a excecao verificada: a chave e sempre um texto fixo e o valor um tipo
 * que o JSON aceita, entao a JSONException so viria de um NaN (um erro de programa).
 */
public final class JsonOut {
    private JsonOut() {}

    public static JSONObject put(JSONObject target, String key, Object value) {
        try {
            target.put(key, value);
        } catch (JSONException error) {
            throw new IllegalArgumentException(error);
        }
        return target;
    }
}
