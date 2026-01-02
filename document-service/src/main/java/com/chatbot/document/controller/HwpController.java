package com.chatbot.document.controller;

import com.chatbot.document.model.ErrorResponse;
import com.chatbot.document.model.HwpExtractionRequest;
import com.chatbot.document.model.HwpExtractionResponse;
import com.chatbot.document.service.HwpExtractionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;
import java.util.Base64;

@Slf4j
@RestController
@RequestMapping("/api/hwp")
@RequiredArgsConstructor
@Tag(name = "HWP Text Extraction", description = "API endpoints for extracting text from Korean HWP files")
public class HwpController {

    private final HwpExtractionService hwpExtractionService;

    @Operation(
            summary = "Health check",
            description = "Check if the HWP service is running and healthy"
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Service is running",
                    content = @Content(schema = @Schema(implementation = String.class)))
    })
    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("HWP Service is running");
    }

    @Operation(
            summary = "Extract text from HWP file",
            description = "Upload an HWP file and extract its text content. Supports HWP files up to 50MB in size."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Text extracted successfully",
                    content = @Content(schema = @Schema(implementation = HwpExtractionResponse.class))),
            @ApiResponse(responseCode = "400", description = "Invalid file format or size",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Extraction failed",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    @PostMapping(value = "/extract", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> extractText(
            @Parameter(description = "HWP file to extract text from (*.hwp, max 50MB)", required = true)
            @RequestParam("file") MultipartFile file) {
        log.info("Received HWP extraction request: {}", file.getOriginalFilename());

        if (!hwpExtractionService.isValidHwpFile(file)) {
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Invalid HWP file")
                            .message("File must be a valid HWP file (*.hwp) and less than 50MB")
                            .path("/api/hwp/extract")
                            .build());
        }

        HwpExtractionResponse response = hwpExtractionService.extractText(file);

        if (!response.isSuccess()) {
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                            .error("Extraction failed")
                            .message("Failed to process HWP file")  // Security: Generic error
                            .path("/api/hwp/extract")
                            .build());
        }

        return ResponseEntity.ok(response);
    }

    @Operation(
            summary = "Extract text from base64-encoded HWP file",
            description = "Send HWP file content as base64-encoded string and extract text. Useful for API integrations where file upload is not available."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Text extracted successfully",
                    content = @Content(schema = @Schema(implementation = HwpExtractionResponse.class))),
            @ApiResponse(responseCode = "400", description = "Invalid request or missing fileContent",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Extraction failed",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    @PostMapping(value = "/extract/base64", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> extractTextFromBase64(
            @Parameter(description = "Extraction request with base64-encoded HWP file content", required = true)
            @Valid @RequestBody HwpExtractionRequest request) {  // Added @Valid
        log.info("Received base64 HWP extraction request: {}", request.getFilename());

        // Security: Validate base64 content size before processing
        if (request.getFileContent().length() > 70000000) {
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Payload too large")
                            .message("Base64 content exceeds maximum size of 50MB")
                            .path("/api/hwp/extract/base64")
                            .build());
        }

        // Security: Validate decoded size (prevent memory exhaustion DoS)
        byte[] fileBytes;
        try {
            fileBytes = Base64.getDecoder().decode(request.getFileContent());

            // Check decoded file size (50MB limit)
            if (fileBytes.length > 50 * 1024 * 1024) {
                return ResponseEntity
                        .badRequest()
                        .body(ErrorResponse.builder()
                                .timestamp(LocalDateTime.now())
                                .status(HttpStatus.BAD_REQUEST.value())
                                .error("File too large")
                                .message("Decoded file size exceeds 50MB limit")
                                .path("/api/hwp/extract/base64")
                                .build());
            }
        } catch (IllegalArgumentException e) {
            log.error("Invalid base64 encoding: {}", e.getMessage());
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Invalid base64")
                            .message("Invalid base64 encoding")
                            .path("/api/hwp/extract/base64")
                            .build());
        }

        HwpExtractionResponse response = hwpExtractionService.extractTextFromBase64(
                request.getFileContent(),
                request.getFilename() != null ? request.getFilename() : "unknown.hwp"
        );

        if (!response.isSuccess()) {
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                            .error("Extraction failed")
                            .message("Failed to process HWP file")  // Security: Generic error
                            .path("/api/hwp/extract/base64")
                            .build());
        }

        return ResponseEntity.ok(response);
    }

    /**
     * Security: Sanitized error handler (prevents information disclosure)
     * Logs full error details server-side, returns generic message to client
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleException(Exception e) {
        // Log full error details server-side for debugging
        log.error("Unexpected error: {}", e.getMessage(), e);

        // Security: Return generic error message (no stack traces or internal details)
        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ErrorResponse.builder()
                        .timestamp(LocalDateTime.now())
                        .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                        .error("Internal Server Error")
                        .message("An unexpected error occurred while processing your request")
                        .path("/api/hwp")
                        .build());
    }
}
