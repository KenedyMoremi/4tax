package ls.fourtax.ussd;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(UssdSettings.class)
public class UssdApplication {
    public static void main(String[] args) {
        var application = new SpringApplication(UssdApplication.class);
        String redisUrl = System.getenv("REDIS_URL");
        // Vercel injects REDIS_URL. Leave Boot's host/port configuration intact when it is absent.
        if (redisUrl != null && !redisUrl.isBlank())
            application.setDefaultProperties(java.util.Map.of("spring.data.redis.url", redisUrl));
        application.run(args);
    }
}
