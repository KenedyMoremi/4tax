package ls.fourtax.ussd.session;

import java.time.Duration;
import java.util.*;
import java.util.function.Supplier;
import ls.fourtax.ussd.UssdSettings;
import ls.fourtax.ussd.journey.State.*;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

@Component
public class RedisSessionStore implements SessionStore {
    private final StringRedisTemplate redis;
    private final JsonMapper json;
    private final Duration ttl;
    public RedisSessionStore(StringRedisTemplate redis, JsonMapper json, UssdSettings settings) {
        this.redis = redis; this.json = json; ttl = Duration.ofSeconds(settings.draftSeconds());
    }
    @Override public <T> T locked(String sessionKey, String mobile, Supplier<T> work) {
        // A caller-wide lock also protects the single resumable draft across simultaneous sessions.
        String key = "lock:" + mobile;
        String token = UUID.randomUUID().toString();
        long until = System.nanoTime() + Duration.ofSeconds(1).toNanos();
        while (!Boolean.TRUE.equals(redis.opsForValue().setIfAbsent(key, token, Duration.ofSeconds(30)))) {
            if (System.nanoTime() >= until) throw new IllegalStateException("Session busy");
            try { Thread.sleep(20); } catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new IllegalStateException("Interrupted"); }
        }
        try { return work.get(); }
        finally { redis.execute(new DefaultRedisScript<>("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end", Long.class), List.of(key), token); }
    }
    @Override public Session session(String key) { return read("session:" + key, Session.class); }
    @Override public void saveSession(String key, Session value) { write("session:" + key, value); }
    @Override public void deleteSession(String key) { redis.delete("session:" + key); }
    @Override public Draft draft(String mobile) { return read("draft:" + mobile, Draft.class); }
    @Override public void saveDraft(String mobile, Draft value) { write("draft:" + mobile, value); }
    @Override public void deleteDraft(String mobile) { redis.delete("draft:" + mobile); }
    @Override public String cached(String key) { return redis.opsForValue().get("reply:" + key); }
    @Override public void cache(String key, String value) { redis.opsForValue().set("reply:" + key, value, ttl); }
    private <T> T read(String key, Class<T> type) {
        String value = redis.opsForValue().get(key); return value == null ? null : json.readValue(value, type);
    }
    private void write(String key, Object value) { redis.opsForValue().set(key, json.writeValueAsString(value), ttl); }
}
