package ls.fourtax.emulator;

import static org.junit.jupiter.api.Assertions.*;
import static ls.fourtax.emulator.Contracts.*;
import org.junit.jupiter.api.Test;

class GrapevineCodecTest {
    final GrapevineCodec codec = new GrapevineCodec();
    static final Subscriber SUBSCRIBER = new Subscriber("test", "+26658123456", "651010000000001", "VOD", "651", "01");
    static ExchangeRequest request(String url, Event event, String input, NumberFormat format, boolean includeId, int timeout) {
        return new ExchangeRequest(url, "X-Gateway-Key", "synthetic-test-key", SUBSCRIBER, "session-1", "request-1", "*123#", event,
                input, format, includeId, "2026-11-19T12:00:00Z", timeout);
    }
    @Test void startIncludesSubscriberAndNetworkMetadataAndStableIds() {
        var request = request("http://localhost/callback", Event.START, "", NumberFormat.INTERNATIONAL, true, 8);
        String xml = codec.encode(request);
        for (String element : new String[]{"<msisdn>26658123456</msisdn>", "<imsi>651010000000001</imsi>",
                "<network>VOD</network>", "<mcc>651</mcc>", "<mnc>01</mnc>", "<code>*123#</code>",
                "<sessionId>session-1</sessionId>", "<requestId>request-1</requestId>", "<type>initial</type>", "<parameter></parameter>"})
            assertTrue(xml.contains(element), element);
        assertEquals(xml, codec.encode(request)); assertFalse(xml.contains("synthetic-test-key"));
        assertEquals("ExchangeRequest[redacted]", request.toString());
    }
    @Test void actionEscapesTextAndCanOmitRequestIds() {
        String xml = codec.encode(request("http://localhost", Event.INPUT, "A & B <C>", NumberFormat.E164, false, 8));
        assertTrue(xml.contains("<name>nextStateAction</name>")); assertTrue(xml.contains("<name>userResponse</name>"));
        assertTrue(xml.contains("A &amp; B &lt;C&gt;")); assertTrue(xml.contains("<msisdn>+26658123456</msisdn>"));
        assertFalse(xml.contains("<requestId>"));
    }
    @Test void localNumbersAndBothAbortReasonsAreSupported() {
        String abort = codec.encode(request("http://localhost", Event.ABORT, "", NumberFormat.LOCAL, true, 8));
        assertTrue(abort.contains("<msisdn>58123456</msisdn>")); assertTrue(abort.contains("<reason>ABORT</reason>"));
        assertTrue(abort.contains("<type>abort</type>"));
        assertTrue(codec.encode(request("http://localhost", Event.TIMEOUT, "", NumberFormat.INTERNATIONAL, true, 8)).contains("<reason>TIMEOUT</reason>"));
    }
    @Test void decodesPromptAndEndStateWithoutExecutingXml() {
        var reply = codec.decode("<ussdAppResponse><prompt>Names &amp; locations</prompt><responseType>string</responseType><state>End</state></ussdAppResponse>");
        assertEquals("Names & locations", reply.prompt()); assertEquals("End", reply.state());
        assertThrows(IllegalArgumentException.class, () -> codec.decode("<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><ussdAppResponse><prompt>&e;</prompt><state>End</state><responseType>string</responseType></ussdAppResponse>"));
        assertThrows(IllegalArgumentException.class, () -> codec.decode("<ussdAppResponse><prompt>x</prompt><state>CON</state><responseType>string</responseType></ussdAppResponse>"));
    }
    @Test void rejectsOversizedInputAndInvalidImsiOrNumber() {
        assertThrows(IllegalArgumentException.class, () -> codec.encode(request("http://localhost", Event.INPUT, "x".repeat(257), NumberFormat.INTERNATIONAL, true, 8)));
        assertThrows(IllegalArgumentException.class, () -> GrapevineCodec.normalize("+26662123456"));
        var r = request("http://localhost", Event.START, "", NumberFormat.INTERNATIONAL, true, 8);
        var invalid = new Subscriber("test", "+26658123456", "651100000000001", "VOD", "651", "01");
        assertThrows(IllegalArgumentException.class, () -> codec.encode(new ExchangeRequest(r.callbackUrl(), r.gatewayHeader(), r.gatewayKey(), invalid,
                r.sessionId(), r.requestId(), r.serviceCode(), r.event(), r.input(), r.numberFormat(), r.includeRequestId(), r.timestamp(), r.timeoutSeconds())));
    }
}
