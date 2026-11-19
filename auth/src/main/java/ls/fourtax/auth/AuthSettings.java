package ls.fourtax.auth;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("auth")
public record AuthSettings(String issuer,
        String keyStore, String keyStorePassword, String keyAlias) {}
