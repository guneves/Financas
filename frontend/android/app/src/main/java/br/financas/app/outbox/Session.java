package br.financas.app.outbox;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Endereco da API e token, para o envio com o app fechado. O login nativo grava os dois
 * (Outbox.signIn) e "Sair" ou um 401 apagam (Outbox.signOut).
 *
 * A chave de acesso remoto (DeviceKey, o X-Device-Key do proxy) mora aqui tambem, mas e do
 * aparelho, nao do login: "Sair" e um 401 do app nao a apagam.
 *
 * O token e a chave ficam cifrados com uma chave do Android Keystore (AES-GCM), que nunca sai
 * do aparelho; o endereco e o usuario ficam em claro.
 */
public final class Session {

    private static final String PREFS = "financas_session";
    private static final String KEY_ALIAS = "financas_session_key";
    private static final String ANDROID_KEYSTORE = "AndroidKeyStore";
    private static final int IV_BYTES = 12;

    private static final String DEVICE_KEY = "device_key";

    public final String baseUrl;
    public final String token;
    public final String userId;
    /** A chave de acesso remoto ("" sem chave). */
    public final String deviceKey;

    private Session(String baseUrl, String token, String userId, String deviceKey) {
        this.baseUrl = baseUrl;
        this.token = token;
        this.userId = userId;
        this.deviceKey = deviceKey == null ? "" : deviceKey;
    }

    /** Uma sessao com estes valores, sem ler o aparelho (os testes dos remetentes). */
    public static Session of(String baseUrl, String token, String userId, String deviceKey) {
        return new Session(baseUrl, token, userId, deviceKey);
    }

    public static synchronized void save(Context context, String baseUrl, String token, String userId) throws Exception {
        prefs(context).edit()
            .putString("base_url", baseUrl)
            .putString("user_id", userId)
            .putString("token", encrypt(token))
            .apply();
    }

    /** "Sair" ou um 401 do app: o login sai, a chave de acesso remoto fica. */
    public static synchronized void clear(Context context) {
        prefs(context).edit().remove("base_url").remove("user_id").remove("token").apply();
    }

    /** Guarda a chave de acesso remoto (cifrada); vazia apaga. */
    public static synchronized void saveDeviceKey(Context context, String key) throws Exception {
        String value = DeviceKey.normalize(key);
        if (value.isEmpty()) {
            prefs(context).edit().remove(DEVICE_KEY).apply();
        } else {
            prefs(context).edit().putString(DEVICE_KEY, encrypt(value)).apply();
        }
    }

    /** A chave de acesso remoto guardada, ou "" (nenhuma, ou nao pode mais ser lida). */
    public static synchronized String deviceKey(Context context) {
        String sealed = prefs(context).getString(DEVICE_KEY, "");
        if (sealed.isEmpty()) return "";
        try {
            return decrypt(sealed);
        } catch (Exception error) {
            return "";
        }
    }

    /**
     * Ao abrir o app: um login guardado com o endereco antigo (443, so na VPN) passa para o
     * padrao do build (ServerAddress).
     */
    public static synchronized void migrateBaseUrl(Context context, String defaultBase) {
        SharedPreferences prefs = prefs(context);
        String stored = prefs.getString("base_url", "");
        String next = ServerAddress.migrate(stored, defaultBase);
        if (next != null && !next.equals(stored)) prefs.edit().putString("base_url", next).apply();
    }

    /** A sessao guardada, ou null se nao ha login (ou o token nao pode mais ser lido). */
    public static synchronized Session load(Context context) {
        SharedPreferences prefs = prefs(context);
        String baseUrl = prefs.getString("base_url", "");
        String userId = prefs.getString("user_id", "");
        String sealed = prefs.getString("token", "");
        if (baseUrl.isEmpty() || userId.isEmpty() || sealed.isEmpty()) return null;
        try {
            return new Session(baseUrl, decrypt(sealed), userId, deviceKey(context));
        } catch (Exception error) {
            // Chave perdida (backup restaurado em outro aparelho, por exemplo): pede login de novo.
            return null;
        }
    }

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance(ANDROID_KEYSTORE);
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) {
            return ((KeyStore.SecretKeyEntry) store.getEntry(KEY_ALIAS, null)).getSecretKey();
        }
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE);
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build());
        return generator.generateKey();
    }

    private static String encrypt(String plain) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] iv = cipher.getIV();
        byte[] sealed = cipher.doFinal(plain.getBytes(StandardCharsets.UTF_8));
        ByteBuffer buffer = ByteBuffer.allocate(iv.length + sealed.length);
        buffer.put(iv).put(sealed);
        return Base64.encodeToString(buffer.array(), Base64.NO_WRAP);
    }

    private static String decrypt(String encoded) throws Exception {
        byte[] all = Base64.decode(encoded, Base64.NO_WRAP);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, all, 0, IV_BYTES));
        byte[] plain = cipher.doFinal(all, IV_BYTES, all.length - IV_BYTES);
        return new String(plain, StandardCharsets.UTF_8);
    }
}
