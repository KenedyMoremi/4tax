package ls.fourtax.ussd.journey;

public record Node(String id, Kind kind, Access access) {
    public enum Kind { MENU, INPUT, ACTION, TERMINAL }
    public enum Access { APPLICATION, OWNER }
    public static Node of(String id) {
        Kind kind = id.startsWith("FIELD:") || id.equals("PIN_NEW") || id.equals("PIN_CONFIRM") || id.equals("LOGIN_PIN") ? Kind.INPUT
                : id.equals("END") ? Kind.TERMINAL : id.equals("SUBMIT") ? Kind.ACTION : Kind.MENU;
        return new Node(id, kind, id.equals("AUTH_MENU") ? Access.OWNER : Access.APPLICATION);
    }
}
