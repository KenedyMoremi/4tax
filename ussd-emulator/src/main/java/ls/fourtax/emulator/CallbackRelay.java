package ls.fourtax.emulator;

import static ls.fourtax.emulator.Contracts.*;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import org.springframework.stereotype.Service;
import tools.jackson.databind.json.JsonMapper;

@Service
public class CallbackRelay {
    private final GrapevineCodec codec;
    private final EmulatorSettings settings;
    private final JsonMapper json = JsonMapper.builder().build();
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER).build();
    public CallbackRelay(GrapevineCodec codec, EmulatorSettings settings) { this.codec = codec; this.settings = settings; }

    public ExchangeReply exchange(ExchangeRequest request) {
        String xml = codec.encode(request);
        URI original = target(request.callbackUrl());
        String allowed = settings.allowedCallbackUrl();
        if (allowed != null && !allowed.isBlank() && !original.equals(URI.create(allowed)))
            throw new IllegalArgumentException("This hosted emulator can only call its configured USSD callback.");
        URI effective = effective(original);
        if (request.inspectBackend()) {
            if (effective.getRawQuery() != null || !effective.getPath().endsWith("/ussd/callback/grapevine"))
                throw new IllegalArgumentException("API inspection requires the 4Tax Grapevine callback without query parameters.");
            effective = URI.create(effective.toString() + "/inspect");
        }
        String key = Objects.requireNonNullElse(request.gatewayKey(), "");
        String header = Objects.requireNonNullElse(request.gatewayHeader(), "X-Gateway-Key");
        if (!header.matches("[A-Za-z][A-Za-z0-9-]{0,63}") || Set.of("host", "content-length", "content-type", "connection", "transfer-encoding", "upgrade", "accept").contains(header.toLowerCase(Locale.ROOT))
                || key.length() > 4096 || key.chars().anyMatch(c -> c < 32 || c == 127))
            throw new IllegalArgumentException("Supply a valid gateway header and value without control characters.");
        var builder = HttpRequest.newBuilder(effective).timeout(Duration.ofSeconds(request.timeoutSeconds()))
                .header("Content-Type", "application/xml; charset=UTF-8").header("Accept", request.inspectBackend() ? "application/json" : "application/xml")
                .POST(HttpRequest.BodyPublishers.ofString(xml, StandardCharsets.UTF_8));
        if (!key.isEmpty()) builder.header(header, key);
        long start = System.nanoTime();
        int status = 0; String responseXml = ""; Map<String, String> headers = new LinkedHashMap<>();
        List<Map<String, Object>> backend = List.of();
        CompletableFuture<HttpResponse<byte[]>> pending = null;
        try {
            pending = http.sendAsync(builder.build(), ignored -> new LimitedBody());
            HttpResponse<byte[]> response = pending.get(request.timeoutSeconds(), TimeUnit.SECONDS);
            status = response.statusCode();
            for (String name : List.of("content-type", "retry-after")) response.headers().firstValue(name).ifPresent(value -> headers.put(name, value));
            responseXml = new String(response.body(), StandardCharsets.UTF_8);
            if (status < 200 || status >= 300) return reply(request, effective, xml, responseXml, status, start, headers, null, "HTTP_ERROR",
                    status == 401 || status == 403 ? "The callback rejected the request. Check its gateway header and key." : "The callback returned HTTP " + status + ".");
            if (request.inspectBackend()) {
                try {
                    var inspection = json.readValue(responseXml, InspectionReply.class);
                    responseXml = Objects.requireNonNull(inspection.responseXml());
                    backend = Objects.requireNonNull(inspection.exchanges());
                } catch (Exception error) {
                    return reply(request, effective, xml, responseXml, status, start, headers, null, "INVALID_RESPONSE",
                            "The callback did not return 4Tax API diagnostics. Disable API inspection for other gateways.");
                }
            }
            GatewayReply decoded;
            try { decoded = codec.decode(responseXml); }
            catch (IllegalArgumentException error) { return reply(request, effective, xml, responseXml, status, start, headers, null, "INVALID_RESPONSE", error.getMessage()); }
            return reply(request, effective, xml, responseXml, status, start, headers, decoded, null, null, backend);
        } catch (TimeoutException error) {
            return reply(request, effective, xml, responseXml, status, start, headers, null, "CALLBACK_TIMEOUT", "Callback timed out. Replay the same request to test recovery.");
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return reply(request, effective, xml, responseXml, status, start, headers, null, "INTERRUPTED", "The callback request was interrupted.");
        } catch (Exception error) {
            for (Throwable cause = error; cause != null; cause = cause.getCause()) {
                if (cause instanceof BodyTooLarge) return reply(request, effective, xml, "", status, start, headers, null, "RESPONSE_TOO_LARGE", "Callback response exceeded 64 KiB.");
                if (cause instanceof HttpTimeoutException) return reply(request, effective, xml, responseXml, status, start, headers, null, "CALLBACK_TIMEOUT", "Callback timed out. Replay the same request to test recovery.");
            }
            return reply(request, effective, xml, responseXml, status, start, headers, null, "CONNECTION_ERROR", "Could not reach the callback. Check its URL and whether the service is running.");
        } finally {
            if (pending != null && !pending.isDone()) pending.cancel(true);
        }
    }
    private URI target(String url) {
        try {
            URI uri = URI.create(url);
            if (!Set.of("http", "https").contains(uri.getScheme()) || uri.getHost() == null
                    || uri.getUserInfo() != null || uri.getFragment() != null || url.length() > 4096) throw new IllegalArgumentException();
            return uri;
        } catch (Exception e) { throw new IllegalArgumentException("Enter an HTTP or HTTPS callback URL without embedded credentials or a fragment."); }
    }
    private URI effective(URI uri) {
        String alias = settings.localhostAlias();
        if (alias == null || alias.isBlank() || !Set.of("localhost", "127.0.0.1", "::1", "[::1]").contains(uri.getHost())) return uri;
        if (!alias.matches("[A-Za-z0-9.-]+")) throw new IllegalArgumentException("Invalid configured localhost alias.");
        return URI.create(uri.getScheme() + "://" + alias + (uri.getPort() < 0 ? "" : ":" + uri.getPort())
                + Objects.requireNonNullElse(uri.getRawPath(), "") + (uri.getRawQuery() == null ? "" : "?" + uri.getRawQuery()));
    }
    private ExchangeReply reply(ExchangeRequest r, URI effective, String requestXml, String responseXml, int status, long start,
            Map<String, String> headers, GatewayReply decoded, String error, String message) {
        return reply(r, effective, requestXml, responseXml, status, start, headers, decoded, error, message, List.of());
    }
    private ExchangeReply reply(ExchangeRequest r, URI effective, String requestXml, String responseXml, int status, long start,
            Map<String, String> headers, GatewayReply decoded, String error, String message, List<Map<String, Object>> backend) {
        return new ExchangeReply(r.callbackUrl(), effective.toString(), r.sessionId(), r.requestId(), r.event().name(), r.timestamp(),
                requestXml, responseXml, status, Duration.ofNanos(System.nanoTime() - start).toMillis(), decoded == null ? null : decoded.prompt(),
                decoded == null ? null : decoded.state(), decoded == null ? null : decoded.responseType(), headers, error, message, backend);
    }
    private static final class BodyTooLarge extends RuntimeException {}
    private static final class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
        private final CompletableFuture<byte[]> result = new CompletableFuture<>();
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        private Flow.Subscription subscription;
        @Override public CompletionStage<byte[]> getBody() { return result; }
        @Override public void onSubscribe(Flow.Subscription value) { subscription = value; value.request(1); }
        @Override public void onNext(List<ByteBuffer> buffers) {
            for (ByteBuffer buffer : buffers) {
                if (buffer.remaining() > 65_536 - bytes.size()) {
                    subscription.cancel(); result.completeExceptionally(new BodyTooLarge()); return;
                }
                byte[] value = new byte[buffer.remaining()]; buffer.get(value); bytes.writeBytes(value);
            }
            subscription.request(1);
        }
        @Override public void onError(Throwable error) { result.completeExceptionally(error); }
        @Override public void onComplete() { result.complete(bytes.toByteArray()); }
    }
}
