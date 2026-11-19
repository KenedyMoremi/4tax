package ls.fourtax.ussd.api;

import static ls.fourtax.ussd.api.Contracts.*;
import java.net.http.HttpClient;
import java.time.*;
import java.util.Map;
import java.util.function.Supplier;
import ls.fourtax.ussd.UssdSettings;
import org.springframework.http.*;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.*;
import tools.jackson.databind.json.JsonMapper;

@Component
public class HttpBackend implements Backend {
    private final RestClient auth;
    private final RestClient registration;
    private final UssdSettings settings;
    private final JsonMapper json;
    private final JwtDecoder owners;
    private String applicationToken;
    private Instant applicationExpiry = Instant.EPOCH;

    public HttpBackend(UssdSettings settings, JsonMapper json) {
        this.settings = settings; this.json = json;
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build());
        factory.setReadTimeout(Duration.ofSeconds(3));
        auth = RestClient.builder().baseUrl(settings.authUrl()).requestFactory(factory).build();
        registration = RestClient.builder().baseUrl(settings.registrationUrl()).requestFactory(factory).build();
        var decoder = NimbusJwtDecoder.withJwkSetUri(settings.jwksUrl()).restOperations(new RestTemplate(factory)).build();
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(JwtValidators.createDefaultWithIssuer(settings.issuer()), jwt ->
                jwt.getAudience().contains("registration-api") && "owner".equals(jwt.getClaimAsString("kind"))
                        && "businesses:create".equals(jwt.getClaimAsString("scope"))
                        ? OAuth2TokenValidatorResult.success() : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token"))));
        owners = decoder;
    }

    @Override public TokenReply createOwner(String mobile, String pin, String operationId) {
        return call(() -> auth.post().uri("/api/v1/auth/owners").headers(h -> h.setBearerAuth(appToken()))
                .header("Idempotency-Key", operationId).body(new PinRequest(mobile, pin)).retrieve().body(TokenReply.class));
    }
    @Override public TokenReply login(String mobile, String pin) {
        return call(() -> auth.post().uri("/api/v1/auth/pin/login").headers(h -> h.setBearerAuth(appToken()))
                .body(new PinRequest(mobile, pin)).retrieve().body(TokenReply.class));
    }
    @Override public RegistrationReply register(String token, BusinessRegistration request, String operationId) {
        verifyOwner(token);
        RegistrationReply reply = call(() -> registration.post().uri("/api/v1/businesses").headers(h -> h.setBearerAuth(token))
                .header("Idempotency-Key", operationId).body(request).retrieve().body(RegistrationReply.class));
        if (reply.entityId() == null || reply.reference() == null || reply.reference().isBlank() || reply.reference().length() > 64)
            throw new Failure("SERVICE_UNAVAILABLE");
        return reply;
    }
    @Override public String verifyOwner(String token) {
        try {
            var jwt = owners.decode(token);
            if (jwt.getExpiresAt() == null || !jwt.getExpiresAt().isAfter(Instant.now()) || jwt.getSubject() == null || jwt.getSubject().isBlank())
                throw new Failure("LOGIN_REQUIRED");
            return jwt.getSubject();
        }
        catch (Exception e) { throw new Failure("LOGIN_REQUIRED"); }
    }

    private synchronized String appToken() {
        if (applicationToken != null && applicationExpiry.isAfter(Instant.now().plusSeconds(15))) return applicationToken;
        var form = new LinkedMultiValueMap<String, String>();
        form.add("grant_type", "client_credentials"); form.add("scope", "owners:create owners:login");
        Map<?, ?> response = auth.post().uri("/oauth2/token")
                .headers(h -> h.setBasicAuth(settings.clientId(), settings.clientSecret()))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED).body(form).retrieve().body(Map.class);
        if (response == null || !(response.get("access_token") instanceof String token)
                || !(response.get("expires_in") instanceof Number expires)) throw new Failure("SERVICE_UNAVAILABLE");
        applicationToken = token; applicationExpiry = Instant.now().plusSeconds(expires.longValue());
        return token;
    }

    private <T> T call(Supplier<T> operation) {
        try {
            T reply = operation.get();
            if (reply == null) throw new Failure("SERVICE_UNAVAILABLE");
            return reply;
        } catch (RestClientResponseException error) {
            try {
                String code = json.readValue(error.getResponseBodyAsString(), ApiError.class).code();
                throw new Failure(code == null ? "SERVICE_UNAVAILABLE" : code);
            }
            catch (Failure failure) { throw failure; }
            catch (Exception ignored) { throw new Failure(error.getStatusCode().value() == 401 ? "LOGIN_REQUIRED" : "SERVICE_UNAVAILABLE"); }
        } catch (RestClientException error) { throw new Failure("SERVICE_UNAVAILABLE"); }
    }
}
