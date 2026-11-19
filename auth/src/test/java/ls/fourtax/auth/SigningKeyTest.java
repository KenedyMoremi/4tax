package ls.fourtax.auth;

import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SigningKeyTest {
    @Test void environmentKeyIsStableAcrossInstancesWithoutLocalFiles() throws Exception {
        var original = new RSAKeyGenerator(2048).keyID("hosted-test").generate();
        var settings = new AuthSettings("https://auth.test", "/nonexistent/keys", "", "signing", original.toJSONString());
        var first = new AuthSecurity().signingKey(settings);
        var second = new AuthSecurity().signingKey(settings);
        assertEquals(first.toJSONString(), second.toJSONString());
        assertEquals(original.toPublicJWK(), first.toPublicJWK());
    }
    @Test void rejectsPublicOrMalformedSigningKeysWithoutEchoingSecrets() throws Exception {
        var publicKey = new RSAKeyGenerator(2048).keyID("public-only").generate().toPublicJWK();
        for (String json : new String[]{publicKey.toJSONString(), "invalid-private-test-secret"}) {
            var settings = new AuthSettings("https://auth.test", "", "", "", json);
            var error = assertThrows(IllegalArgumentException.class, () -> new AuthSecurity().signingKey(settings));
            assertFalse(error.getMessage().contains(json));
        }
    }
}
