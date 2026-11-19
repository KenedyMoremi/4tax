package ls.fourtax.ussd.journey;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import ls.fourtax.ussd.UssdSettings;
import org.springframework.stereotype.Component;

@Component
public class Crypto {
    private final byte[] secret;
    public Crypto(UssdSettings settings) { secret = settings.stateSecret().getBytes(StandardCharsets.UTF_8); }
    public String digest(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256"); mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) { throw new IllegalStateException("Cannot protect session state", e); }
    }
    public boolean matches(String digest, String value) {
        return digest != null && MessageDigest.isEqual(digest.getBytes(StandardCharsets.UTF_8), digest(value).getBytes(StandardCharsets.UTF_8));
    }
}
