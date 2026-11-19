package ls.fourtax.ussd.api;

import static ls.fourtax.ussd.api.Contracts.*;
import java.net.http.HttpClient;
import java.time.*;
import java.util.*;
import java.util.function.*;
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
    private final ApiTrace trace;
    private final JwtDecoder owners;
    private String applicationToken;
    private Instant applicationExpiry = Instant.EPOCH;

    public HttpBackend(UssdSettings settings, JsonMapper json, ApiTrace trace) {
        this.settings = settings; this.json = json; this.trace = trace;
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(settings.connectTimeout()).build());
        factory.setReadTimeout(settings.requestTimeout());
        auth = RestClient.builder().baseUrl(settings.authUrl()).requestFactory(factory).build();
        registration = RestClient.builder().baseUrl(settings.registrationUrl()).requestFactory(factory).build();
        var keys = new RestTemplate(factory);
        keys.getInterceptors().add((request, body, execution) -> {
            long start = System.nanoTime();
            try {
                var response = execution.execute(request, body);
                trace.add("signing-keys", "GET", settings.jwksUrl(), response.getStatusCode().value(), start, Map.of(),
                        Map.of("body", "[public signing keys omitted]"), response.getStatusCode().is2xxSuccessful() ? "OK" : "HTTP_ERROR");
                return response;
            } catch (java.io.IOException error) {
                trace.add("signing-keys", "GET", settings.jwksUrl(), 0, start, Map.of(), Map.of(), "CONNECTION_OR_TIMEOUT");
                throw error;
            }
        });
        var decoder = NimbusJwtDecoder.withJwkSetUri(settings.jwksUrl()).restOperations(keys).build();
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(JwtValidators.createDefaultWithIssuer(settings.issuer()), jwt ->
                jwt.getAudience().contains("registration-api") && "owner".equals(jwt.getClaimAsString("kind"))
                        && Arrays.asList(Objects.requireNonNullElse(jwt.getClaimAsString("scope"), "").split(" ")).contains("businesses:create")
                        ? OAuth2TokenValidatorResult.success() : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token"))));
        owners = decoder;
    }

    @Override public TokenReply createOwner(String mobile, String pin, String operationId) {
        String app = appToken(); // A token failure is a separate stage, before owner creation.
        return call("create-owner", settings.authUrl(), "/api/v1/auth/owners", pinPreview(),
                () -> auth.post().uri("/api/v1/auth/owners").headers(h -> h.setBearerAuth(app))
                        .header("Idempotency-Key", operationId).body(new PinRequest(mobile, pin)).retrieve().toEntity(TokenReply.class),
                HttpBackend::tokenPreview);
    }
    @Override public TokenReply login(String mobile, String pin) {
        String app = appToken();
        return call("pin-login", settings.authUrl(), "/api/v1/auth/pin/login", pinPreview(),
                () -> auth.post().uri("/api/v1/auth/pin/login").headers(h -> h.setBearerAuth(app))
                        .body(new PinRequest(mobile, pin)).retrieve().toEntity(TokenReply.class), HttpBackend::tokenPreview);
    }
    @Override public RegistrationReply register(String token, BusinessRegistration request, String operationId) {
        if ("example.com".equalsIgnoreCase(java.net.URI.create(settings.registrationUrl()).getHost()))
            throw new Failure("SERVICE_UNAVAILABLE");
        verifyOwner(token);
        RegistrationReply reply = call("register-business", settings.registrationUrl(), "/api/v1/businesses", ApiTrace.registration(request),
                () -> registration.post().uri("/api/v1/businesses").headers(h -> h.setBearerAuth(token))
                        .header("Idempotency-Key", operationId).body(request).retrieve().toEntity(RegistrationReply.class), Function.identity());
        if (reply.entityId() == null || reply.reference() == null || reply.reference().isBlank() || reply.reference().length() > 64)
            throw new Failure("SERVICE_UNAVAILABLE");
        return reply;
    }
    @Override public String verifyOwner(String token) {
        long start = System.nanoTime();
        try {
            var jwt = owners.decode(token);
            if (jwt.getExpiresAt() == null || !jwt.getExpiresAt().isAfter(Instant.now()) || jwt.getSubject() == null || jwt.getSubject().isBlank())
                throw new Failure("LOGIN_REQUIRED");
            trace.add("verify-owner-token", "LOCAL", settings.jwksUrl(), 0, start, Map.of("token", "[redacted]"),
                    Map.of("issuer", settings.issuer(), "audience", "registration-api"), "VERIFIED");
            return jwt.getSubject();
        } catch (Exception e) {
            trace.add("verify-owner-token", "LOCAL", settings.jwksUrl(), 0, start, Map.of("token", "[redacted]"),
                    Map.of("expectedIssuer", settings.issuer(), "expectedAudience", "registration-api"), "JWT_REJECTED_OR_JWKS_UNAVAILABLE");
            throw new Failure("LOGIN_REQUIRED");
        }
    }

    private synchronized String appToken() {
        if (applicationToken != null && applicationExpiry.isAfter(Instant.now().plusSeconds(15))) return applicationToken;
        var form = new LinkedMultiValueMap<String, String>();
        form.add("grant_type", "client_credentials"); form.add("scope", "owners:create owners:login");
        Map<?, ?> response = call("application-token", settings.authUrl(), "/oauth2/token", Map.of(
                "grant_type", "client_credentials", "scope", "owners:create owners:login"),
                () -> auth.post().uri("/oauth2/token").headers(h -> h.setBasicAuth(settings.clientId(), settings.clientSecret()))
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED).body(form).retrieve().toEntity(Map.class),
                HttpBackend::applicationPreview);
        if (!(response.get("access_token") instanceof String token) || token.isBlank()
                || !(response.get("expires_in") instanceof Number expires) || expires.longValue() <= 0)
            throw new Failure("SERVICE_UNAVAILABLE");
        applicationToken = token; applicationExpiry = Instant.now().plusSeconds(expires.longValue());
        return token;
    }

    private <T> T call(String stage, String base, String path, Object preview,
            Supplier<ResponseEntity<T>> operation, Function<T, ?> sanitize) {
        long start = System.nanoTime();
        try {
            var response = operation.get(); T body = response.getBody();
            trace.add(stage, "POST", base + path, response.getStatusCode().value(), start, preview,
                    body == null ? Map.of() : sanitize.apply(body), body == null ? "INVALID_RESPONSE" : "OK");
            if (body == null) throw new Failure("SERVICE_UNAVAILABLE");
            return body;
        } catch (RestClientResponseException error) {
            String code = "SERVICE_UNAVAILABLE"; List<String> fields = List.of();
            try {
                var body = json.readTree(error.getResponseBodyAsString());
                String candidate = body.path("code").asText(body.path("error").asText(""));
                if (candidate.matches("[A-Za-z_]{1,64}")) code = candidate;
                if (body.path("fields").isObject()) {
                    var names = new ArrayList<String>();
                    for (String key : body.path("fields").propertyNames())
                        if (key.matches("[A-Za-z0-9_.-]{1,100}") && names.size() < 50) names.add(key);
                    fields = names;
                }
            } catch (Exception ignored) { /* Arbitrary upstream bodies can contain credentials or personal data. */ }
            trace.add(stage, "POST", base + path, error.getStatusCode().value(), start, preview,
                    Map.of("code", code, "invalidFields", fields), "HTTP_ERROR");
            // Login failures must retain INVALID_CREDENTIALS, rather than masquerading as expired bearer auth.
            throw new Failure(error.getStatusCode().value() == 401 && !code.equals("INVALID_CREDENTIALS") ? "LOGIN_REQUIRED" : code);
        } catch (RestClientException error) {
            boolean timeout = false;
            for (Throwable cause = error; cause != null; cause = cause.getCause())
                if (cause instanceof java.net.http.HttpTimeoutException || cause instanceof java.net.SocketTimeoutException) timeout = true;
            trace.add(stage, "POST", base + path, 0, start, preview, Map.of(), timeout ? "TIMEOUT" : "CONNECTION_OR_RESPONSE_ERROR");
            throw new Failure("SERVICE_UNAVAILABLE");
        }
    }
    private static Object pinPreview() { return Map.of("mobileNumber", "[redacted]", "pin", "[redacted]"); }
    private static Object applicationPreview(Map<?, ?> body) {
        Map<String, Object> preview = new LinkedHashMap<>();
        if (body.containsKey("access_token")) preview.put("access_token", "[redacted]");
        if (body.containsKey("expires_in")) preview.put("expires_in", body.get("expires_in") instanceof Number n ? n : "[invalid]");
        if (body.containsKey("token_type")) preview.put("token_type", "Bearer".equalsIgnoreCase(String.valueOf(body.get("token_type"))) ? "Bearer" : "[invalid]");
        return preview;
    }
    private static Object tokenPreview(TokenReply token) {
        return Map.of("ownerId", "[redacted]", "accessToken", "[redacted]", "tokenType", "Bearer", "expiresIn", token.expiresIn());
    }
}
