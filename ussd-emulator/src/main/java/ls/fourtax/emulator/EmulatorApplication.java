package ls.fourtax.emulator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(EmulatorSettings.class)
public class EmulatorApplication {
    public static void main(String[] args) { SpringApplication.run(EmulatorApplication.class, args); }
}
