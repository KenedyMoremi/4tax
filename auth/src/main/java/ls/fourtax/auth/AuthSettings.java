package ls.fourtax.auth;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("auth")
public record AuthSettings(String issuer,
        String keyStore, String keyStorePassword, String keyAlias, String signingJwk) {
    @Override public String toString() { return "AuthSettings[issuer=" + issuer + ", signing credentials=REDACTED]"; }
}
