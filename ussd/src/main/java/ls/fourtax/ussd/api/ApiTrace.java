package ls.fourtax.ussd.api;

import java.util.*;
import org.springframework.stereotype.Component;

/** Opt-in, request-local diagnostics. Never persisted or logged; never accepts raw credentials. */
@Component
public class ApiTrace {
    public record Exchange(String stage, String method, String url, int httpStatus, long durationMs,
            Map<String, String> requestHeaders, Object requestBody, Object responseBody, String outcome) {}
    private final ThreadLocal<List<Exchange>> current = new ThreadLocal<>();
    public Capture begin() {
        if (current.get() != null) throw new IllegalStateException("Trace already active");
        current.set(new ArrayList<>()); return new Capture();
    }
    public void add(String stage, String method, String url, int status, long start, Object request, Object response, String outcome) {
        var entries = current.get();
        if (entries != null && entries.size() < 20) {
            Map<String, String> headers = new LinkedHashMap<>();
            if (method.equals("POST")) {
                headers.put("Content-Type", stage.equals("application-token") ? "application/x-www-form-urlencoded" : "application/json");
                headers.put("Authorization", "[redacted]");
                if (Set.of("create-owner", "register-business").contains(stage))
                    headers.put("Idempotency-Key", "[redacted: stable operation key]");
            }
            if (method.equals("GET")) headers.put("Accept", "application/json");
            entries.add(new Exchange(stage, method, url, status, (System.nanoTime() - start) / 1_000_000, headers, request, response, outcome));
        }
    }
    public final class Capture implements AutoCloseable {
        public List<Exchange> exchanges() { return List.copyOf(current.get()); }
        @Override public void close() { current.remove(); }
    }
    // Keep schema, choices and amounts visible. Free text/identifiers are never copied into diagnostics.
    public static Map<String, Object> registration(Contracts.BusinessRegistration body) {
        var details = new LinkedHashMap<String, Object>();
        Set<String> safe = Set.of("business_type", "service_type", "goods_type", "activity", "turnover_range",
                "working_days", "opens_at", "closes_at", "overnight", "service_price_range", "purchase_price_range",
                "selling_price_range", "shipping_price_range", "farmland_count", "farmland_size", "farmland_unit");
        body.details().forEach((key, value) -> details.put(key, safe.contains(key) || "".equals(value) ? value : "[redacted]"));
        var result = new LinkedHashMap<String, Object>();
        result.put("sector", body.sector()); result.put("owner", Map.of("idNumber", "[redacted]", "fullNames", "[redacted]"));
        result.put("details", details); result.put("employees", rows(body.employees(), Set.of("salary_range")));
        if (body.routes() != null) result.put("routes", rows(body.routes(), Set.of("price")));
        if (body.livestock() != null) result.put("livestock", rows(body.livestock(), Set.of("number")));
        result.put("source", body.source()); return result;
    }
    private static List<Map<String, String>> rows(List<Map<String, String>> rows, Set<String> safe) {
        return rows.stream().map(row -> {
            Map<String, String> copy = new LinkedHashMap<>();
            row.forEach((key, value) -> copy.put(key, safe.contains(key) ? value : "[redacted]")); return copy;
        }).toList();
    }
}
