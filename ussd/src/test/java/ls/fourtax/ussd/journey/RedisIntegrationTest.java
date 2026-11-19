package ls.fourtax.ussd.journey;

import static org.junit.jupiter.api.Assertions.*;
import static ls.fourtax.ussd.journey.TestSupport.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import ls.fourtax.ussd.callback.Callback;
import ls.fourtax.ussd.session.RedisSessionStore;
import org.junit.jupiter.api.*;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.*;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class RedisIntegrationTest {
    @Container static final GenericContainer<?> REDIS = new GenericContainer<>("redis:8-alpine").withExposedPorts(6379);
    LettuceConnectionFactory connection;
    StringRedisTemplate redis;
    Driver d;
    @BeforeEach void setup() {
        connection = new LettuceConnectionFactory(REDIS.getHost(), REDIS.getMappedPort(6379)); connection.afterPropertiesSet(); connection.start();
        redis = new StringRedisTemplate(connection); redis.getConnectionFactory().getConnection().serverCommands().flushDb();
        d = new Driver(new RedisSessionStore(redis, JsonMapper.builder().build(), settings()), new FakeBackend());
    }
    @AfterEach void close() { connection.destroy(); }
    @Test void fullJourneyUsesRedisWithoutPersistingRawPinAndDraftHasTtl() {
        d.transportToReview("1"); d.steps("1", "087431");
        for (String key : redis.keys("*")) {
            if (!key.startsWith("lock:")) assertFalse(Objects.requireNonNull(redis.opsForValue().get(key)).contains("087431"));
        }
        Long ttl = redis.getExpire("draft:" + d.crypto.digest(d.mobile)); assertNotNull(ttl); assertTrue(ttl > 880 && ttl <= 900);
        d.input("087431"); assertTrue(d.last.end()); assertTrue(redis.keys("draft:*").isEmpty()); assertTrue(redis.keys("session:*").isEmpty());
    }
    @Test void concurrentDuplicateCallbacksAdvanceOnlyOnce() throws Exception {
        d.start();
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Callable<Callback.Reply> work = () -> d.coordinator.handle(new Callback("test", "TEST", d.sessionId, d.mobile,
                    Callback.Event.INPUT, "1", "*123#", "duplicate"));
            var results = executor.invokeAll(List.of(work, work));
            assertEquals(results.getFirst().get(), results.getLast().get()); assertEquals("MAIN", d.state().node);
        }
        assertTrue(redis.keys("lock:*").isEmpty());
    }
    @Test void redisDraftExpiryCannotBeExtendedByAnInvalidInput() throws Exception {
        d.transportToReview("1");
        redis.expire("draft:" + d.crypto.digest(d.mobile), Duration.ofMillis(10)); Thread.sleep(40);
        d.input("invalid"); assertTrue(d.last.end()); assertNull(d.store.draft(d.crypto.digest(d.mobile)));
    }
    @Test void applicationStartsWithHostAndPortWhenRedisUrlIsAbsent() {
        var application = new org.springframework.boot.SpringApplication(ls.fourtax.ussd.UssdApplication.class);
        try (var context = application.run("--server.port=0", "--spring.data.redis.host=" + REDIS.getHost(),
                "--spring.data.redis.port=" + REDIS.getMappedPort(6379), "--spring.data.redis.password=",
                "--ussd.gateway-key=" + settings().gatewayKey(), "--ussd.state-secret=" + settings().stateSecret(),
                "--ussd.auth-url=https://auth.example.test", "--ussd.issuer=https://auth.example.test",
                "--ussd.jwks-url=https://auth.example.test/oauth2/jwks", "--ussd.client-id=test", "--ussd.client-secret=test",
                "--ussd.registration-url=https://registration.example.test")) {
            assertEquals("PONG", context.getBean(StringRedisTemplate.class).execute((org.springframework.data.redis.core.RedisCallback<String>) c -> c.ping()));
        }
    }
    @Test void transactionRecoveryRetainsOperationButNeverPinOrJwtInTheDraft() {
        d.backend.pins.put(d.mobile,"001234");
        d.backend.ownedBusinesses.add(new ls.fourtax.ussd.api.Contracts.BusinessSummary("business-1","4TAX-TEST","retail","Test shop"));
        d.start(); d.steps("1","001234","2","Synthetic goods","M100 total","paid in cash","-","1");
        assertEquals("TX_PREVIEW",d.state().node);
        String key="transaction:"+d.crypto.digest(d.mobile);
        String draft=redis.opsForValue().get(key); assertNotNull(draft); assertFalse(draft.contains("001234")); assertFalse(draft.contains("owner-token"));
        assertTrue(redis.getExpire(key)>880);
        d.backend.loseTransactionReply=true; d.input("1"); assertEquals("TX_RETRY",d.state().node);
        d.input("99"); d.start(); d.steps("2","001234","2","1","1");
        assertEquals("TX_DONE",d.state().node); assertEquals(1,d.backend.postedTransactions.size()); assertTrue(redis.opsForValue().get(key).contains("posted"));
        d.input("2"); assertNull(redis.opsForValue().get(key));
    }

}
