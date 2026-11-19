package ls.fourtax.ussd.journey;

import java.text.MessageFormat;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class Messages {
    public String text(String language, String key, Object... args) {
        ResourceBundle bundle = ResourceBundle.getBundle("messages", Locale.forLanguageTag(language));
        return new MessageFormat(bundle.getString(key).replace("'", "''"), Locale.forLanguageTag(language)).format(args);
    }
}
