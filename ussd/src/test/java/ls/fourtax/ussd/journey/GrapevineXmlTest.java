package ls.fourtax.ussd.journey;

import static org.junit.jupiter.api.Assertions.*;
import ls.fourtax.ussd.callback.*;
import org.junit.jupiter.api.Test;

class GrapevineXmlTest {
    final GrapevineXml xml = new GrapevineXml();
    @Test void parsesPublishedInitialActionAndAbortShapes() {
        String base = "<msisdn>26658123456</msisdn><sessionId>123</sessionId><network>VOD</network>";
        assertEquals(Callback.Event.START, xml.parse("<ussdAppRequest>" + base + "<type>initial</type><code>*123#</code></ussdAppRequest>").event());
        var action = xml.parse("<ussdAppRequest>" + base + "<type>action</type><name>nextStateAction</name><fields><field><name>userResponse</name><value>012345</value></field></fields></ussdAppRequest>");
        assertEquals(Callback.Event.INPUT, action.event()); assertEquals("012345", action.input());
        assertEquals(Callback.Event.ABORT, xml.parse("<ussdAppRequest>" + base + "<type>abort</type><reason>TIMEOUT</reason></ussdAppRequest>").event());
        assertTrue(xml.render(new Callback.Reply("A & B <C>", false)).contains("A &amp; B &lt;C&gt;"));
        assertTrue(xml.render(new Callback.Reply("Done", true)).contains("<state>End</state>"));
    }
    @Test void rejectsMalformedXmlExternalEntitiesAndAmbiguousFields() {
        assertThrows(IllegalArgumentException.class, () -> xml.parse("<broken"));
        assertThrows(IllegalArgumentException.class, () -> xml.parse("<!DOCTYPE x [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><ussdAppRequest><type>&xxe;</type></ussdAppRequest>"));
        assertThrows(IllegalArgumentException.class, () -> xml.parse("<ussdAppRequest><type>initial</type><type>abort</type></ussdAppRequest>"));
    }
}
