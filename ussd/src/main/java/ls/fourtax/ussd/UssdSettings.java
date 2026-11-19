package ls.fourtax.ussd;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("ussd")
public record UssdSettings(String gatewayKey, String stateSecret, int screenLimit, long draftSeconds,
        String authUrl, String issuer, String jwksUrl, String clientId, String clientSecret, String registrationUrl) {
    public UssdSettings {
        if (gatewayKey == null || gatewayKey.length() < 24 || stateSecret == null || stateSecret.length() < 32)
            throw new IllegalArgumentException("Configure GATEWAY_KEY (24+ characters) and STATE_SECRET (32+ characters)");
        if (screenLimit < 120 || screenLimit > 182 || draftSeconds < 60 || draftSeconds > 900)
            throw new IllegalArgumentException("Screen limit must be 120..182; draft TTL must be 60..900 seconds");
    }
}
