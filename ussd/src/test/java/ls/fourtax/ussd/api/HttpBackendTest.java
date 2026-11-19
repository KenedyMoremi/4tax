package ls.fourtax.ussd.api;

import static ls.fourtax.ussd.api.Contracts.*;
import static ls.fourtax.ussd.journey.TestSupport.*;
import static org.junit.jupiter.api.Assertions.*;
import com.nimbusds.jose.*;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.*;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.*;
import com.sun.net.httpserver.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import ls.fourtax.ussd.UssdSettings;
import org.junit.jupiter.api.*;
import tools.jackson.databind.json.JsonMapper;

class HttpBackendTest {
    HttpServer server;
    ExecutorService executor;
    JsonMapper json = JsonMapper.builder().build();
    RSAKey key;
    String base, ownerToken;
    ApiTrace trace;
    HttpBackend backend;
    List<String> ownerBodies = new CopyOnWriteArrayList<>(), businessBodies = new CopyOnWriteArrayList<>(), operationKeys = new CopyOnWriteArrayList<>();
    AtomicInteger tokenCalls = new AtomicInteger();
    int tokenStatus = 200, businessStatus = 201;
    long tokenDelay;
    @BeforeEach void setup() throws Exception {
        key = new RSAKeyGenerator(2048).keyID("test-only").generate();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        executor = Executors.newVirtualThreadPerTaskExecutor(); server.setExecutor(executor);
        base = "http://127.0.0.1:" + server.getAddress().getPort();
        ownerToken = jwt(base, "registration-api", "owner", "businesses:create", Instant.now().plusSeconds(900), key);
        server.createContext("/oauth2/jwks", e -> send(e, 200, new JWKSet(key.toPublicJWK()).toString()));
        server.createContext("/oauth2/token", e -> {
            tokenCalls.incrementAndGet();
            assertEquals("Basic " + Base64.getEncoder().encodeToString("test-client:test-secret".getBytes(StandardCharsets.UTF_8)), e.getRequestHeaders().getFirst("Authorization"));
            String body = new String(e.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(body.contains("grant_type=client_credentials")); assertTrue(body.contains("owners%3Acreate"));
            try { Thread.sleep(tokenDelay); } catch (InterruptedException error) { Thread.currentThread().interrupt(); }
            send(e, tokenStatus, tokenStatus == 200 ? "{\"access_token\":\"private-application-token\",\"expires_in\":300}" : "{\"error\":\"invalid_client\",\"error_description\":\"do not expose\"}");
        });
        server.createContext("/api/v1/auth/owners", e -> {
            assertEquals("Bearer private-application-token", e.getRequestHeaders().getFirst("Authorization"));
            ownerBodies.add(new String(e.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            operationKeys.add(e.getRequestHeaders().getFirst("Idempotency-Key"));
            send(e, 201, json.writeValueAsString(new TokenReply("00000000-0000-0000-0000-000000000001", ownerToken, "Bearer", 900)));
        });
        server.createContext("/api/v1/auth/pin/login", e -> {
            e.getRequestBody().readAllBytes(); send(e, 401, "{\"code\":\"INVALID_CREDENTIALS\",\"message\":\"private response\"}");
        });
        server.createContext("/api/v1/businesses", e -> {
            assertEquals("Bearer " + ownerToken, e.getRequestHeaders().getFirst("Authorization"));
            businessBodies.add(new String(e.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            operationKeys.add(e.getRequestHeaders().getFirst("Idempotency-Key"));
            send(e, businessStatus, businessStatus == 201 ? "{\"entityId\":\"00000000-0000-0000-0000-000000000002\",\"reference\":\"4TAX-TEST\"}"
                    : "{\"code\":\"VALIDATION_ERROR\",\"message\":\"private response\",\"fields\":{\"details.vin\":\"private VIN\"}}");
        });
        server.start(); trace = new ApiTrace(); backend = backend(Duration.ofSeconds(5));
    }
    HttpBackend backend(Duration timeout) {
        var s = settings(); return new HttpBackend(new UssdSettings(s.gatewayKey(), s.stateSecret(), 160, 900,
                base, base, base + "/oauth2/jwks", "test-client", "test-secret", base, Duration.ofSeconds(1), timeout), json, trace);
    }
    @AfterEach void stop() { if (server != null) server.stop(0); if (executor != null) executor.close(); }
    static void send(HttpExchange e, int status, String body) throws java.io.IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8); e.getResponseHeaders().set("Content-Type", "application/json");
        e.sendResponseHeaders(status, bytes.length); try { e.getResponseBody().write(bytes); } finally { e.close(); }
    }
    @Test void allJourneysSendTheRealWireContractAndStableKeysWithoutLeakingSecrets() throws Exception {
        List<Object> samples = new ArrayList<>();
        for (String language : List.of("1", "2")) for (int sector = 1; sector <= 5; sector++) {
            var fake = new FakeBackend(); var d = new Driver(new MemoryStore(), fake);
            d.start(); d.steps(language, "1", String.valueOf(sector)); d.fillToReview(); d.steps("1", "001234", "001234");
            var payload = fake.saved.values().iterator().next(); String operation = UUID.randomUUID().toString();
            try (var capture = trace.begin()) {
                var account = backend.createOwner("+26658123456", "001234", operation);
                backend.register(account.accessToken(), payload, operation);
                backend.register(account.accessToken(), payload, operation); // Transport retry retains the exact serialized body/key.
                String snapshot = json.writeValueAsString(capture.exchanges());
                for (String secret : List.of("001234", "+26658123456", "private-application-token", ownerToken,
                        "test-secret", "Mpho Example", "000123456789", "Synthetic Employee", "VIN00000000000001"))
                    assertFalse(snapshot.contains(secret));
                assertTrue(snapshot.contains("register-business")); assertTrue(snapshot.contains("\"Idempotency-Key\""));
            }
            var owner = json.readTree(ownerBodies.getLast());
            assertEquals("001234", owner.get("pin").asText()); assertEquals("+26658123456", owner.get("mobileNumber").asText());
            assertEquals(businessBodies.get(businessBodies.size()-2), businessBodies.getLast());
            var wire = json.readTree(businessBodies.getLast());
            assertEquals("000123456789", wire.get("owner").get("idNumber").asText());
            assertTrue(wire.get("employees").isArray());
            assertEquals(sector == 1, wire.has("routes")); assertEquals(sector == 5, wire.has("livestock"));
            assertFalse(wire.has("ownerId")); assertFalse(wire.has("schemaVersion"));
            assertEquals(operation, operationKeys.getLast()); samples.add(wire);
        }
        assertEquals(1, tokenCalls.get());
        Files.createDirectories(Path.of("target"));
        Files.writeString(Path.of("target/registration-wire-samples.json"), json.writeValueAsString(samples));
    }
    @Test void authClientFailureIsAttributedBeforeAnyOwnerOrRegistrationRequest() {
        tokenStatus = 401;
        try (var capture = trace.begin()) {
            assertThrows(Backend.Failure.class, () -> backend.createOwner("+26658123456", "001234", "operation"));
            assertTrue(ownerBodies.isEmpty()); assertTrue(businessBodies.isEmpty());
            assertEquals(1, capture.exchanges().size()); var failure = capture.exchanges().getFirst();
            assertEquals("application-token", failure.stage()); assertEquals(401, failure.httpStatus());
            assertTrue(json.writeValueAsString(failure.responseBody()).contains("invalid_client"));
            assertFalse(json.writeValueAsString(failure).contains("do not expose"));
        }
    }
    @Test void slowColdStartWorksWithinConfiguredTimeoutAndTimeoutPreservesStage() {
        tokenDelay = 3200;
        assertNotNull(backend.createOwner("+26658123456", "001234", "operation"));
        backend = backend(Duration.ofMillis(100));
        try (var capture = trace.begin()) {
            assertThrows(Backend.Failure.class, () -> backend.createOwner("+26658123456", "001234", "operation"));
            assertEquals("TIMEOUT", capture.exchanges().getFirst().outcome());
            assertEquals("application-token", capture.exchanges().getFirst().stage());
        }
    }
    @Test void validationErrorsRetainFieldNamesAndLoginFailuresRetainTheirCode() {
        var failure = assertThrows(Backend.Failure.class, () -> backend.login("+26658123456", "001234"));
        assertEquals("INVALID_CREDENTIALS", failure.code);
        var fake = new FakeBackend(); var d = new Driver(new MemoryStore(), fake);
        d.transportToReview("1"); d.steps("1", "001234", "001234"); businessStatus = 422;
        try (var capture = trace.begin()) {
            assertEquals("VALIDATION_ERROR", assertThrows(Backend.Failure.class,
                    () -> backend.register(ownerToken, fake.saved.values().iterator().next(), "operation")).code);
            String snapshot = json.writeValueAsString(capture.exchanges());
            assertTrue(snapshot.contains("details.vin")); assertFalse(snapshot.contains("private VIN"));
        }
    }
    @Test void ownerTokensEnforceSignatureIssuerAudienceKindScopeAndExpiry() throws Exception {
        assertNotNull(backend.verifyOwner(ownerToken));
        var other = new RSAKeyGenerator(2048).keyID("other").generate();
        for (String token : List.of(jwt("https://wrong.test", "registration-api", "owner", "businesses:create", Instant.now().plusSeconds(60), key),
                jwt(base, "wrong", "owner", "businesses:create", Instant.now().plusSeconds(60), key),
                jwt(base, "registration-api", "application", "businesses:create", Instant.now().plusSeconds(60), key),
                jwt(base, "registration-api", "owner", "owners:create", Instant.now().plusSeconds(60), key),
                jwt(base, "registration-api", "owner", "businesses:create", Instant.now().minusSeconds(120), key),
                jwt(base, "registration-api", "owner", "businesses:create", Instant.now().plusSeconds(60), other)))
            assertThrows(Backend.Failure.class, () -> backend.verifyOwner(token));
        assertNotNull(backend.verifyOwner(jwt(base, "registration-api", "owner", "businesses:create businesses:read", Instant.now().plusSeconds(60), key)));
    }
    String jwt(String issuer, String aud, String kind, String scope, Instant expiry, RSAKey signingKey) throws Exception {
        var claims = new JWTClaimsSet.Builder().issuer(issuer).subject("00000000-0000-0000-0000-000000000001")
                .audience(aud).expirationTime(Date.from(expiry)).claim("kind", kind).claim("scope", scope).build();
        var jwt = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(signingKey.getKeyID()).build(), claims);
        jwt.sign(new RSASSASigner(signingKey)); return jwt.serialize();
    }
}
