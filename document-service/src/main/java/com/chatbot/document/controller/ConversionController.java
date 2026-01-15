package com.chatbot.document.controller;

import com.chatbot.document.model.ErrorResponse;
import com.chatbot.document.model.HtmlConversionRequest;
import com.chatbot.document.service.HtmlToHwpxConversionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

@Slf4j
@RestController
@RequestMapping("/api/conversion")
@RequiredArgsConstructor
@Validated
@Tag(name = "Document Conversion", description = "Document format conversion APIs")
public class ConversionController {

    private final HtmlToHwpxConversionService conversionService;

    @PostMapping(value = "/html-to-hwpx", produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    @Operation(summary = "Convert HTML to HWPX", description = "Convert HTML content to HWPX (Hangul Word Processor X) format")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Successfully converted HTML to HWPX",
                    content = @Content(mediaType = MediaType.APPLICATION_OCTET_STREAM_VALUE)),
            @ApiResponse(responseCode = "400", description = "Invalid request",
                    content = @Content(mediaType = MediaType.APPLICATION_JSON_VALUE,
                            schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Internal server error",
                    content = @Content(mediaType = MediaType.APPLICATION_JSON_VALUE,
                            schema = @Schema(implementation = ErrorResponse.class)))
    })
    public ResponseEntity<?> convertHtmlToHwpx(@Valid @RequestBody HtmlConversionRequest request) {
        try {
            log.info("Received HTML to HWPX conversion request");

            // Validate HTML content
            if (request.getHtmlContent() == null || request.getHtmlContent().trim().isEmpty()) {
                return ResponseEntity
                        .badRequest()
                        .body(ErrorResponse.builder()
                                .error("HTML content is required")
                                .timestamp(LocalDateTime.now())
                                .build());
            }

            // Convert HTML to HWPX
            byte[] hwpxBytes = conversionService.convertHtmlToHwpx(request.getHtmlContent());

            // Generate filename
            String filename = request.getFilename() != null && !request.getFilename().trim().isEmpty()
                    ? request.getFilename()
                    : generateDefaultFilename();

            if (!filename.toLowerCase().endsWith(".hwpx")) {
                filename += ".hwpx";
            }

            // Prepare response headers
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
            headers.setContentDispositionFormData("attachment",
                    URLEncoder.encode(filename, StandardCharsets.UTF_8));
            headers.setContentLength(hwpxBytes.length);

            log.info("Successfully converted HTML to HWPX: {} bytes, filename: {}",
                    hwpxBytes.length, filename);

            return ResponseEntity
                    .ok()
                    .headers(headers)
                    .body(hwpxBytes);

        } catch (Exception e) {
            log.error("HTML to HWPX conversion failed: {}", e.getMessage(), e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .error("HTML to HWPX conversion failed: " + e.getMessage())
                            .timestamp(LocalDateTime.now())
                            .build());
        }
    }

    @PostMapping(value = "/markdown-to-hwpx", produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    @Operation(summary = "Convert Markdown to HWPX", description = "Convert Markdown content to HWPX (Hangul Word Processor X) format")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Successfully converted Markdown to HWPX",
                    content = @Content(mediaType = MediaType.APPLICATION_OCTET_STREAM_VALUE)),
            @ApiResponse(responseCode = "400", description = "Invalid request",
                    content = @Content(mediaType = MediaType.APPLICATION_JSON_VALUE,
                            schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Internal server error",
                    content = @Content(mediaType = MediaType.APPLICATION_JSON_VALUE,
                            schema = @Schema(implementation = ErrorResponse.class)))
    })
    public ResponseEntity<?> convertMarkdownToHwpx(@Valid @RequestBody HtmlConversionRequest request) {
        try {
            log.info("Received Markdown to HWPX conversion request");

            // Validate content
            String content = request.getMarkdownContent() != null && !request.getMarkdownContent().trim().isEmpty()
                    ? request.getMarkdownContent()
                    : request.getHtmlContent();

            if (content == null || content.trim().isEmpty()) {
                return ResponseEntity
                        .badRequest()
                        .body(ErrorResponse.builder()
                                .error("Markdown content is required")
                                .timestamp(LocalDateTime.now())
                                .build());
            }

            // Convert Markdown to HWPX
            byte[] hwpxBytes = conversionService.convertMarkdownToHwpx(content);

            // Generate filename
            String filename = request.getFilename() != null && !request.getFilename().trim().isEmpty()
                    ? request.getFilename()
                    : generateDefaultFilename();

            if (!filename.toLowerCase().endsWith(".hwpx")) {
                filename += ".hwpx";
            }

            // Prepare response headers
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
            headers.setContentDispositionFormData("attachment",
                    URLEncoder.encode(filename, StandardCharsets.UTF_8));
            headers.setContentLength(hwpxBytes.length);

            log.info("Successfully converted Markdown to HWPX: {} bytes, filename: {}",
                    hwpxBytes.length, filename);

            return ResponseEntity
                    .ok()
                    .headers(headers)
                    .body(hwpxBytes);

        } catch (Exception e) {
            log.error("Markdown to HWPX conversion failed: {}", e.getMessage(), e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .error("Markdown to HWPX conversion failed: " + e.getMessage())
                            .timestamp(LocalDateTime.now())
                            .build());
        }
    }

    /**
     * Generate default filename with timestamp
     */
    private String generateDefaultFilename() {
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd_HH-mm-ss");
        return "document_" + LocalDateTime.now().format(formatter) + ".hwpx";
    }
}
