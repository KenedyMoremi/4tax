package ls.fourtax.auth;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.*;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.*;
import org.testcontainers.postgresql.PostgreSQLContainer;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ExtendWith(OutputCaptureExtension.class)
class AuthIntegrationTest {
    @Container static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:17-alpine");
    static final String PASSWORD = "test-keystore-password-1234567890";
    static final Path KEYSTORE = keyStore();
    @DynamicPropertySource static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("auth.issuer", () -> "http://fourtax.test");
        registry.add("auth.key-store", KEYSTORE::toString);
        registry.add("auth.key-store-password", () -> PASSWORD);
    }
    static Path keyStore() {
        try {
            Path path = Files.createTempDirectory("fourtax-test-key").resolve("signing.p12");
            var process = new ProcessBuilder(System.getProperty("java.home") + "/bin/keytool", "-genkeypair", "-alias", "signing",
                    "-keyalg", "RSA", "-keysize", "2048", "-storetype", "PKCS12", "-keystore", path.toString(),
                    "-storepass", PASSWORD, "-dname", "CN=Test", "-validity", "1")
                    .redirectOutput(ProcessBuilder.Redirect.DISCARD).redirectError(ProcessBuilder.Redirect.DISCARD).start();
            if (process.waitFor() != 0) throw new IllegalStateException("Test signing key generation failed");
            return path;
        } catch (Exception error) { throw new ExceptionInInitializerError(error); }
    }

    @LocalServerPort int port;
    @Autowired JsonMapper json;
    @Autowired JdbcTemplate db;
    @Autowired JwtEncoder signer;
    final HttpClient http = HttpClient.newHttpClient();

    Map<?, ?> provision() throws Exception {
        var result = request("/api/v1/clients", Map.of("applicationName", "Test client", "scopes", List.of("owners:create", "owners:login")), null, null);
        assertEquals(201, result.statusCode());
        assertEquals("no-store", result.headers().firstValue("Cache-Control").orElseThrow());
        return json.readValue(result.body(), Map.class);
    }
    String applicationToken(Map<?, ?> client) throws Exception {
        String basic = Base64.getEncoder().encodeToString((client.get("clientId") + ":" + client.get("clientSecret")).getBytes(StandardCharsets.UTF_8));
        var response = http.send(HttpRequest.newBuilder(URI.create(base() + "/oauth2/token"))
                .header("Authorization", "Basic " + basic).header("Content-Type", "application/x-www-form-urlencoded")
                .POST(HttpRequest.BodyPublishers.ofString("grant_type=client_credentials&scope=owners:create%20owners:login")).build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode(), response.body());
        return (String) json.readValue(response.body(), Map.class).get("access_token");
    }
    HttpResponse<String> request(String path, Object body, String token, String key) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create(base() + path)).header("Content-Type", "application/json");
        if (token != null) builder.header("Authorization", "Bearer " + token);
        if (key != null) builder.header("Idempotency-Key", key);
        return http.send(builder.POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build(), HttpResponse.BodyHandlers.ofString());
    }
    String base() { return "http://localhost:" + port; }
    String phone() { return "+2665" + String.format("%07d", Math.abs(UUID.randomUUID().hashCode()) % 10_000_000); }

    @Test void publicProvisioningIssuesUniqueCredentialsAndStoresOnlyHashes() throws Exception {
        Map<?, ?> first = provision(); Map<?, ?> second = provision();
        assertNotEquals(first.get("clientId"), second.get("clientId"));
        assertNotEquals(first.get("clientSecret"), second.get("clientSecret"));
        String stored = db.queryForObject("select client_secret from oauth2_registered_client where client_id = ?", String.class, first.get("clientId"));
        assertNotEquals(first.get("clientSecret"), stored); assertTrue(stored.startsWith("$2a$12$"));
        String jwt = applicationToken(first);
        var decoded = NimbusJwtDecoder.withJwkSetUri(base() + "/oauth2/jwks").build().decode(jwt);
        assertEquals("application", decoded.getClaimAsString("kind")); assertEquals(List.of("auth-api"), decoded.getAudience());
        assertEquals(300, Duration.between(decoded.getIssuedAt(), decoded.getExpiresAt()).toSeconds());
        var metadata = http.send(HttpRequest.newBuilder(URI.create(base() + "/.well-known/oauth-authorization-server")).GET().build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, metadata.statusCode()); assertTrue(metadata.body().contains("http://fourtax.test"));
    }

    @Test void ownerCreationIsIdempotentAndCannotOverwriteAnExistingPin(CapturedOutput output) throws Exception {
        String application = applicationToken(provision()); String mobile = phone(); String key = UUID.randomUUID().toString();
        var body = new Contracts.PinRequest(mobile, "087431");
        var first = request("/api/v1/auth/owners", body, application, key);
        var second = request("/api/v1/auth/owners", body, application, key);
        assertEquals(201, first.statusCode(), first.body()); assertEquals(201, second.statusCode());
        Map<?, ?> owner = json.readValue(first.body(), Map.class);
        assertEquals(owner.get("ownerId"), json.readValue(second.body(), Map.class).get("ownerId"));
        assertEquals(1, db.queryForObject("select count(*) from owner_credentials where mobile_number = ?", Integer.class, mobile));
        assertNotEquals("087431", db.queryForObject("select pin_hash from owner_credentials where mobile_number = ?", String.class, mobile));
        var changed = request("/api/v1/auth/owners", new Contracts.PinRequest(mobile, "987654"), application, key);
        assertEquals(409, changed.statusCode()); assertTrue(changed.body().contains("IDEMPOTENCY_CONFLICT"));
        var exists = request("/api/v1/auth/owners", body, application, UUID.randomUUID().toString());
        assertEquals(409, exists.statusCode()); assertTrue(exists.body().contains("OWNER_EXISTS"));
        var login = request("/api/v1/auth/pin/login", body, application, null);
        assertEquals(200, login.statusCode());
        String token = (String) json.readValue(login.body(), Map.class).get("accessToken");
        var decoded = NimbusJwtDecoder.withJwkSetUri(base() + "/oauth2/jwks").build().decode(token);
        assertEquals(owner.get("ownerId"), decoded.getSubject()); assertEquals(List.of("registration-api"), decoded.getAudience());
        assertEquals(Set.of("businesses:create", "businesses:read", "transactions:create"), Set.of(decoded.getClaimAsString("scope").split(" ")));
        assertEquals(900, Duration.between(decoded.getIssuedAt(), decoded.getExpiresAt()).toSeconds());
        assertEquals(401, request("/api/v1/auth/owners", body, token, UUID.randomUUID().toString()).statusCode());
        assertEquals(401, request("/api/v1/auth/pin/login", body, null, null).statusCode());
        assertFalse(output.getAll().contains("087431"));
        assertFalse(output.getAll().contains(token));
    }

    @Test void failedAttemptsCommitAndLockExpires() throws Exception {
        String token = applicationToken(provision()); String mobile = phone();
        request("/api/v1/auth/owners", new Contracts.PinRequest(mobile, "087431"), token, UUID.randomUUID().toString());
        for (int i = 1; i <= 5; i++) {
            var response = request("/api/v1/auth/pin/login", new Contracts.PinRequest(mobile, "111111"), token, null);
            assertEquals(i == 5 ? 423 : 401, response.statusCode());
        }
        assertEquals(5, db.queryForObject("select failed_attempts from owner_credentials where mobile_number = ?", Integer.class, mobile));
        assertEquals(423, request("/api/v1/auth/pin/login", new Contracts.PinRequest(mobile, "087431"), token, null).statusCode());
        db.update("update owner_credentials set locked_until = current_timestamp - interval '1 second' where mobile_number = ?", mobile);
        assertEquals(200, request("/api/v1/auth/pin/login", new Contracts.PinRequest(mobile, "087431"), token, null).statusCode());
        assertEquals(0, db.queryForObject("select failed_attempts from owner_credentials where mobile_number = ?", Integer.class, mobile));
    }

    @Test void concurrentAccountCreationReturnsOneOwner() throws Exception {
        String token = applicationToken(provision()); String mobile = phone(); String key = UUID.randomUUID().toString();
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Callable<HttpResponse<String>> work = () -> request("/api/v1/auth/owners", new Contracts.PinRequest(mobile, "087431"), token, key);
            var replies = executor.invokeAll(List.of(work, work));
            assertEquals(201, replies.get(0).get().statusCode()); assertEquals(201, replies.get(1).get().statusCode());
            assertEquals(1, db.queryForObject("select count(*) from owner_credentials where mobile_number = ?", Integer.class, mobile));
        }
    }
    @Test void lookupIsApplicationProtectedNormalizedAndDoesNotChangeLoginAttempts() throws Exception {
        String application = applicationToken(provision()); String mobile = phone();
        var request = new Contracts.OwnerLookup(mobile);
        assertEquals(401, request("/api/v1/auth/owners/lookup", request, null, null).statusCode());
        var absent = request("/api/v1/auth/owners/lookup", request, application, null);
        assertEquals(200, absent.statusCode()); assertTrue(absent.body().contains("false"));
        var created = request("/api/v1/auth/owners", new Contracts.PinRequest(mobile, "001234"), application, UUID.randomUUID().toString());
        String ownerToken = (String) json.readValue(created.body(), Map.class).get("accessToken");
        assertEquals(401, request("/api/v1/auth/owners/lookup", request, ownerToken, null).statusCode());
        var registered = request("/api/v1/auth/owners/lookup", new Contracts.OwnerLookup(mobile.substring(4)), application, null);
        assertEquals(200, registered.statusCode()); assertTrue(registered.body().contains("true"));
        assertEquals("no-store", registered.headers().firstValue("Cache-Control").orElseThrow());
        assertFalse(registered.body().contains("ownerId"));
        assertEquals(0, db.queryForObject("select failed_attempts from owner_credentials where mobile_number = ?", Integer.class, mobile));
        assertEquals(400, request("/api/v1/auth/owners/lookup", new Contracts.OwnerLookup("invalid"), application, null).statusCode());
    }
    @Test void rejectsWrongIssuerAudienceExpirySignatureAndScope() throws Exception {
        var body = new Contracts.PinRequest(phone(), "087431");
        Instant now = Instant.now();
        for (String variant : List.of("issuer", "audience", "expired", "signature", "scope")) {
            var claims = JwtClaimsSet.builder().issuer(variant.equals("issuer") ? "http://wrong.test" : "http://fourtax.test")
                    .subject("test-client").audience(List.of(variant.equals("audience") ? "wrong-api" : "auth-api"))
                    .issuedAt(now.minusSeconds(3600)).expiresAt(variant.equals("expired") ? now.minusSeconds(1) : now.plusSeconds(300))
                    .claim("kind", "application").claim("scope", variant.equals("scope") ? "owners:create" : "owners:login").build();
            String token = signer.encode(JwtEncoderParameters.from(JwsHeader.with(SignatureAlgorithm.RS256).build(), claims)).getTokenValue();
            if (variant.equals("signature")) {
                int at = token.lastIndexOf('.') + 12;
                token = token.substring(0, at) + (token.charAt(at) == 'A' ? 'B' : 'A') + token.substring(at + 1);
            }
            assertEquals(variant.equals("scope") ? 403 : 401, request("/api/v1/auth/pin/login", body, token, null).statusCode(), variant);
        }
    }
}
