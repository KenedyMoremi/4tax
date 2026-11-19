package ls.fourtax.emulator;

import static ls.fourtax.emulator.Contracts.*;
import static ls.fourtax.emulator.GrapevineCodecTest.request;
import static org.junit.jupiter.api.Assertions.*;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.*;

class CallbackRelayTest {
    HttpServer server;
    ExecutorService executor;
    CallbackRelay relay;
    List<String> bodies = new CopyOnWriteArrayList<>();
    String base;
    static final String GOOD = "<ussdAppResponse><prompt>4Tax\n1 English\n2 Sesotho</prompt><responseType>string</responseType><state>NextState</state></ussdAppResponse>";
    @BeforeEach void setup() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        executor = Executors.newVirtualThreadPerTaskExecutor(); server.setExecutor(executor);
        server.createContext("/callback", exchange -> {
            assertEquals("synthetic-test-key", exchange.getRequestHeaders().getFirst("X-Gateway-Key"));
            bodies.add(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] response = GOOD.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/xml"); exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response); exchange.close();
        });
        server.start(); base = "http://127.0.0.1:" + server.getAddress().getPort();
        relay = new CallbackRelay(new GrapevineCodec(), new EmulatorSettings(base, "*123#", "", ""));
    }
    @AfterEach void stop() { server.stop(0); executor.close(); }
    @Test void postsXmlAndReplayPreservesTheExactWireEnvelope() {
        var r = request(base + "/callback?test=one", Event.START, "", NumberFormat.INTERNATIONAL, true, 8);
        var reply = relay.exchange(r); var replay = relay.exchange(r);
        assertNull(reply.errorCode()); assertEquals(200, reply.httpStatus()); assertEquals("NextState", reply.state());
        assertTrue(reply.prompt().contains("English")); assertEquals("application/xml", reply.responseHeaders().get("content-type"));
        assertEquals(bodies.getFirst(), bodies.getLast()); assertEquals(reply.requestXml(), replay.requestXml());
        assertFalse(reply.toString().contains("synthetic-test-key"));
    }
    @Test void retainsHttpFailuresAndMalformedResponsesForInspection() {
        server.createContext("/denied", exchange -> { exchange.sendResponseHeaders(401, -1); exchange.close(); });
        var denied = relay.exchange(request(base + "/denied", Event.START, "", NumberFormat.INTERNATIONAL, true, 8));
        assertEquals(401, denied.httpStatus()); assertEquals("HTTP_ERROR", denied.errorCode()); assertNull(denied.state());
        server.createContext("/html", exchange -> {
            byte[] value = "<html>Wrong endpoint</html>".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, value.length); exchange.getResponseBody().write(value); exchange.close();
        });
        var invalid = relay.exchange(request(base + "/html", Event.START, "", NumberFormat.INTERNATIONAL, true, 8));
        assertEquals("INVALID_RESPONSE", invalid.errorCode()); assertTrue(invalid.responseXml().contains("Wrong endpoint"));
    }
    @Test void neverFollowsRedirectsWithGatewayCredentials() {
        AtomicInteger redirected = new AtomicInteger();
        server.createContext("/redirect", exchange -> {
            exchange.getResponseHeaders().set("Location", base + "/target"); exchange.sendResponseHeaders(302, -1); exchange.close();
        });
        server.createContext("/target", exchange -> { redirected.incrementAndGet(); exchange.sendResponseHeaders(200, -1); exchange.close(); });
        var reply = relay.exchange(request(base + "/redirect", Event.START, "", NumberFormat.INTERNATIONAL, true, 8));
        assertEquals(302, reply.httpStatus()); assertEquals(0, redirected.get());
    }
    @Test void timeoutIncludesAStalledResponseBody() {
        server.createContext("/slow", exchange -> {
            exchange.sendResponseHeaders(200, 100);
            exchange.getResponseBody().write('x'); exchange.getResponseBody().flush();
            try { Thread.sleep(1400); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            exchange.close();
        });
        var reply = relay.exchange(request(base + "/slow", Event.START, "", NumberFormat.INTERNATIONAL, true, 1));
        assertEquals("CALLBACK_TIMEOUT", reply.errorCode()); assertTrue(reply.durationMs() < 2500);
    }
    @Test void limitsResponseSizeBeforeBufferingTheWholeBody() {
        server.createContext("/large", exchange -> {
            byte[] data = new byte[70_000]; exchange.sendResponseHeaders(200, data.length);
            try { exchange.getResponseBody().write(data); } finally { exchange.close(); }
        });
        var reply = relay.exchange(request(base + "/large", Event.START, "", NumberFormat.INTERNATIONAL, true, 8));
        assertEquals("RESPONSE_TOO_LARGE", reply.errorCode());
    }
    @Test void hostedCallbackAllowlistBlocksOtherHostsPathsAndQueries() {
        relay = new CallbackRelay(new GrapevineCodec(), new EmulatorSettings(base, "*123#", "", base + "/callback"));
        for (String target : List.of("http://169.254.169.254/latest/meta-data", base + "/other", base + "/callback?redirect=1"))
            assertThrows(IllegalArgumentException.class, () -> relay.exchange(request(target, Event.START, "", NumberFormat.INTERNATIONAL, true, 8)));
        assertEquals(200, relay.exchange(request(base + "/callback", Event.START, "", NumberFormat.INTERNATIONAL, true, 8)).httpStatus());
    }
    @Test void validatesTargetUrlsBeforeMakingNetworkCalls() {
        for (String target : List.of("file:///etc/passwd", "ftp://localhost/a", "http://name:secret@localhost/callback", "http://localhost/callback#fragment"))
            assertThrows(IllegalArgumentException.class, () -> relay.exchange(request(target, Event.START, "", NumberFormat.INTERNATIONAL, true, 8)));
    }
    @Test void inspectionReturnsXmlAndEveryDownstreamExchangeWithinTheSameAllowlist() {
        var json = tools.jackson.databind.json.JsonMapper.builder().build();
        server.createContext("/ussd/callback/grapevine/inspect", exchange -> {
            assertEquals("synthetic-test-key", exchange.getRequestHeaders().getFirst("X-Gateway-Key"));
            assertEquals("application/json", exchange.getRequestHeaders().getFirst("Accept"));
            bodies.add(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] response = json.writeValueAsBytes(Map.of("responseXml", GOOD, "exchanges", List.of(
                    Map.of("stage", "application-token", "httpStatus", 401, "outcome", "HTTP_ERROR",
                            "requestBody", Map.of("grant_type", "client_credentials"), "responseBody", Map.of("code", "invalid_client")))));
            exchange.getResponseHeaders().set("Content-Type", "application/json"); exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response); exchange.close();
        });
        String url = base + "/ussd/callback/grapevine";
        relay = new CallbackRelay(new GrapevineCodec(), new EmulatorSettings(base, "*123#", "", url));
        var r = request(url, Event.INPUT, "1", NumberFormat.INTERNATIONAL, true, 120);
        var inspected = new ExchangeRequest(r.callbackUrl(), r.gatewayHeader(), r.gatewayKey(), r.subscriber(), r.sessionId(),
                r.requestId(), r.serviceCode(), r.event(), r.input(), r.numberFormat(), r.includeRequestId(), r.timestamp(), r.timeoutSeconds(), true);
        var reply = relay.exchange(inspected);
        assertNull(reply.errorCode()); assertEquals(GOOD, reply.responseXml()); assertEquals("NextState", reply.state());
        assertEquals(1, reply.backendExchanges().size()); assertEquals(401, reply.backendExchanges().getFirst().get("httpStatus"));
        assertEquals(url + "/inspect", reply.effectiveUrl()); assertEquals(reply.requestXml(), bodies.getLast());
    }
}
