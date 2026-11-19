package ls.fourtax.ussd;

import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;

@ConfigurationProperties("ussd")
public record UssdSettings(String gatewayKey, String stateSecret, int screenLimit, long draftSeconds,
        String authUrl, String issuer, String jwksUrl, String clientId, String clientSecret, String registrationUrl,
        Duration connectTimeout, Duration requestTimeout) {
    public UssdSettings(String gatewayKey, String stateSecret, int screenLimit, long draftSeconds,
            String authUrl, String issuer, String jwksUrl, String clientId, String clientSecret, String registrationUrl) {
        this(gatewayKey, stateSecret, screenLimit, draftSeconds, authUrl, issuer, jwksUrl, clientId, clientSecret,
                registrationUrl, Duration.ofSeconds(5), Duration.ofSeconds(30));
    }
    @org.springframework.boot.context.properties.bind.ConstructorBinding
    public UssdSettings {
        if (connectTimeout == null) connectTimeout = Duration.ofSeconds(5);
        if (requestTimeout == null) requestTimeout = Duration.ofSeconds(30);
        if (connectTimeout.isNegative() || connectTimeout.isZero() || connectTimeout.compareTo(Duration.ofSeconds(10)) > 0
                || requestTimeout.isNegative() || requestTimeout.isZero() || requestTimeout.compareTo(Duration.ofSeconds(60)) > 0)
            throw new IllegalArgumentException("Connect timeout must be positive and at most 10s; request timeout at most 60s");
        if (gatewayKey == null || gatewayKey.length() < 24 || stateSecret == null || stateSecret.length() < 32)
            throw new IllegalArgumentException("Configure GATEWAY_KEY (24+ characters) and STATE_SECRET (32+ characters)");
        if (screenLimit < 120 || screenLimit > 182 || draftSeconds < 60 || draftSeconds > 900)
            throw new IllegalArgumentException("Screen limit must be 120..182; draft TTL must be 60..900 seconds");
    }
    public Duration processingLease() { return connectTimeout.plus(requestTimeout).multipliedBy(6).plusSeconds(30); }
}
