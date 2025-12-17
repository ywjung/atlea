package com.chatbot.hwp.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

/**
 * OpenAPI (Swagger) configuration for HWP service API documentation
 */
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI hwpServiceOpenAPI() {
        Server localServer = new Server();
        localServer.setUrl("http://localhost:8081");
        localServer.setDescription("Local Development Server");

        Contact contact = new Contact();
        contact.setName("HWP Service Team");
        contact.setEmail("support@example.com");

        License license = new License()
                .name("MIT License")
                .url("https://opensource.org/licenses/MIT");

        Info info = new Info()
                .title("HWP Text Extraction Service API")
                .version("1.0.0")
                .description("REST API for extracting text content from Korean HWP (Hangul Word Processor) files. " +
                        "This service processes HWP files and returns extracted text for RAG chatbot indexing.")
                .contact(contact)
                .license(license);

        return new OpenAPI()
                .info(info)
                .servers(List.of(localServer));
    }
}
