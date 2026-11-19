package ls.fourtax.ussd;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(UssdSettings.class)
public class UssdApplication {
    public static void main(String[] args) { SpringApplication.run(UssdApplication.class, args); }
}
