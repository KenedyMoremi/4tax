package ls.fourtax.emulator;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("emulator")
public record EmulatorSettings(String defaultCallbackUrl, String defaultServiceCode, String localhostAlias) {}
