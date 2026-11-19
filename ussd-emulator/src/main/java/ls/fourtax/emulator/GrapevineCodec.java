package ls.fourtax.emulator;

import static ls.fourtax.emulator.Contracts.*;
import java.io.StringReader;
import java.time.Instant;
import java.util.*;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.springframework.stereotype.Component;
import org.w3c.dom.*;
import org.xml.sax.InputSource;
import org.xml.sax.helpers.DefaultHandler;

@Component
public class GrapevineCodec {
    public String encode(ExchangeRequest request) {
        validate(request);
        Subscriber subscriber = request.subscriber();
        String number = normalize(subscriber.mobileNumber());
        number = switch (request.numberFormat()) {
            case INTERNATIONAL -> number.substring(1);
            case E164 -> number;
            case LOCAL -> number.substring(4);
        };
        String type = switch (request.event()) { case START -> "initial"; case INPUT -> "action"; default -> "abort"; };
        StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<ussdAppRequest>\n");
        tag(xml, "msisdn", number); tag(xml, "imsi", subscriber.imsi()); tag(xml, "sessionId", request.sessionId());
        tag(xml, "network", subscriber.network()); tag(xml, "mcc", subscriber.mcc()); tag(xml, "mnc", subscriber.mnc());
        tag(xml, "code", request.serviceCode()); tag(xml, "type", type); tag(xml, "timestamp", request.timestamp());
        if (request.includeRequestId()) tag(xml, "requestId", request.requestId());
        switch (request.event()) {
            case START -> tag(xml, "parameter", "");
            case INPUT -> {
                tag(xml, "name", "nextStateAction");
                xml.append("  <fields><field><name>userResponse</name><value>").append(escape(request.input()))
                        .append("</value></field></fields>\n");
            }
            case ABORT -> tag(xml, "reason", "ABORT");
            case TIMEOUT -> tag(xml, "reason", "TIMEOUT");
        }
        return xml.append("</ussdAppRequest>").toString();
    }
    public GatewayReply decode(String xml) {
        if (xml == null || xml.length() > 65_536) throw new IllegalArgumentException("Callback response is too large.");
        try {
            var factory = DocumentBuilderFactory.newInstance();
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, ""); factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            factory.setExpandEntityReferences(false); factory.setXIncludeAware(false);
            var builder = factory.newDocumentBuilder(); builder.setErrorHandler(new DefaultHandler());
            Element root = builder.parse(new InputSource(new StringReader(xml))).getDocumentElement();
            if (!root.getTagName().equals("ussdAppResponse")) throw new IllegalArgumentException();
            String state = child(root, "state"); String prompt = child(root, "prompt");
            String responseType = child(root, "responseType");
            if (!Set.of("NextState", "End").contains(state) || !responseType.equals("string")) throw new IllegalArgumentException();
            return new GatewayReply(prompt, state, responseType);
        } catch (Exception error) { throw new IllegalArgumentException("Expected a Grapevine ussdAppResponse with prompt, responseType=string and state=NextState or End."); }
    }
    private void validate(ExchangeRequest r) {
        if (r == null || r.subscriber() == null || r.event() == null || r.numberFormat() == null)
            throw new IllegalArgumentException("Subscriber, event and number format are required.");
        Subscriber s = r.subscriber(); normalize(s.mobileNumber());
        if (!"651".equals(s.mcc()) || !Set.of("01", "10").contains(Objects.requireNonNullElse(s.mnc(), ""))
                || !"VOD".equals(s.network()) || s.imsi() == null || !s.imsi().matches("[0-9]{15}")
                || !s.imsi().startsWith(s.mcc() + s.mnc()))
            throw new IllegalArgumentException("Use a 15-digit Vodacom test IMSI beginning with MCC 651 and MNC 01 or 10, and network VOD.");
        if (r.sessionId() == null || !r.sessionId().matches("[A-Za-z0-9._:-]{1,128}")
                || (r.includeRequestId() && (r.requestId() == null || !r.requestId().matches("[A-Za-z0-9._:-]{1,128}"))))
            throw new IllegalArgumentException("Session and request IDs must contain 1–128 letters, digits, dots, colons, underscores or hyphens.");
        if (r.serviceCode() == null || !r.serviceCode().matches("\\*[0-9*]{1,30}#"))
            throw new IllegalArgumentException("Enter a USSD service code such as *123#.");
        if (r.input() == null || r.input().length() > 256 || r.input().chars().anyMatch(c -> c < 32 || c == 127))
            throw new IllegalArgumentException("Input must contain at most 256 characters without control characters.");
        if (r.timeoutSeconds() < 1 || r.timeoutSeconds() > 120) throw new IllegalArgumentException("Callback timeout must be 1–120 seconds.");
        try { Instant.parse(r.timestamp()); } catch (Exception e) { throw new IllegalArgumentException("A valid ISO timestamp is required."); }
    }
    static String normalize(String value) {
        String number = value == null ? "" : value.replaceAll("[ +()-]", "");
        if (number.matches("5[0-9]{7}")) number = "266" + number;
        if (!number.matches("2665[0-9]{7}")) throw new IllegalArgumentException("Use an eight-digit Lesotho mobile number beginning with 5, optionally prefixed with +266.");
        return "+" + number;
    }
    private String child(Element parent, String name) {
        String value = null;
        for (org.w3c.dom.Node child = parent.getFirstChild(); child != null; child = child.getNextSibling()) {
            if (child instanceof Element element && element.getTagName().equals(name)) {
                if (value != null) throw new IllegalArgumentException(); value = element.getTextContent();
            }
        }
        if (value == null) throw new IllegalArgumentException(); return value;
    }
    private void tag(StringBuilder xml, String name, String value) { xml.append("  <").append(name).append(">").append(escape(value)).append("</").append(name).append(">\n"); }
    private String escape(String value) { return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&apos;"); }
}
