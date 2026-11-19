package ls.fourtax.ussd.callback;

import static ls.fourtax.ussd.callback.Callback.*;
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.*;
import org.xml.sax.InputSource;
import org.xml.sax.helpers.DefaultHandler;

/** Published Grapevine v1.3 prototype adapter; operator contracts still require confirmation. */
public final class GrapevineXml {
    public Callback parse(String xml) {
        if (xml == null || xml.length() > 16_384) throw new IllegalArgumentException("Invalid callback XML");
        try {
            var factory = DocumentBuilderFactory.newInstance();
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, ""); factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            factory.setXIncludeAware(false); factory.setExpandEntityReferences(false);
            var builder = factory.newDocumentBuilder(); builder.setErrorHandler(new DefaultHandler());
            Element root = builder.parse(new InputSource(new StringReader(xml))).getDocumentElement();
            if (!root.getTagName().equals("ussdAppRequest")) throw new IllegalArgumentException();
            Event event = switch (text(root, "type")) {
                case "initial" -> Event.START; case "action" -> Event.INPUT; case "abort" -> Event.ABORT;
                default -> throw new IllegalArgumentException();
            };
            String input = text(root, "parameter");
            if (event == Event.INPUT) {
                if (!text(root, "name").equals("nextStateAction")) throw new IllegalArgumentException();
                NodeList fields = root.getElementsByTagName("field");
                if (fields.getLength() != 1) throw new IllegalArgumentException();
                Element field = (Element) fields.item(0);
                if (!text(field, "name").equals("userResponse")) throw new IllegalArgumentException();
                input = text(field, "value");
            }
            return new Callback("grapevine", text(root, "network"), text(root, "sessionId"), text(root, "msisdn"), event,
                    input, text(root, "code"), text(root, "requestId"));
        } catch (Exception error) { throw new IllegalArgumentException("Invalid callback XML"); }
    }
    private String text(Element parent, String tag) {
        String value = null;
        for (org.w3c.dom.Node child = parent.getFirstChild(); child != null; child = child.getNextSibling()) {
            if (child instanceof Element element && element.getTagName().equals(tag)) {
                if (value != null) throw new IllegalArgumentException(); value = element.getTextContent();
            }
        }
        return value == null ? "" : value;
    }
    public String render(Reply reply) {
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?><ussdAppResponse><prompt>" + escape(reply.message())
                + "</prompt><responseType>string</responseType><state>" + (reply.end() ? "End" : "NextState") + "</state></ussdAppResponse>";
    }
    private String escape(String value) { return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&apos;"); }
}
