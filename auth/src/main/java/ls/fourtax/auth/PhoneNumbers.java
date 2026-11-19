package ls.fourtax.auth;

final class PhoneNumbers {
    private PhoneNumbers() {}
    static String normalize(String value) {
        if (value == null) throw new IllegalArgumentException("Invalid mobile number");
        String number = value.strip().replaceAll("[ ()-]", "");
        if (number.matches("[0-9]{8}")) number = "+266" + number;
        else if (number.startsWith("00")) number = "+" + number.substring(2);
        else if (!number.startsWith("+")) number = "+" + number;
        if (!number.matches("\\+[1-9][0-9]{7,14}")) throw new IllegalArgumentException("Invalid mobile number");
        return number;
    }
}
