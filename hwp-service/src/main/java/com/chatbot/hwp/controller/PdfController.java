package com.chatbot.hwp.controller;

import com.chatbot.hwp.model.ErrorResponse;
import com.chatbot.hwp.model.PdfExtractionRequest;
import com.chatbot.hwp.model.PdfExtractionResponse;
import com.chatbot.hwp.service.PdfExtractionService;
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
@RequestMapping("/api/pdf")
@RequiredArgsConstructor
@Tag(name = "PDF Text Extraction", description = "API endpoints for extracting text from PDF files with optional chunking")
public class PdfController {

    private final PdfExtractionService pdfExtractionService;

    @Operation(
            summary = "Health check",
            description = "Check if the PDF service is running and healthy"
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Service is running",
                    content = @Content(schema = @Schema(implementation = String.class)))
    })
    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("PDF Service is running");
    }

    @Operation(
            summary = "Extract text from PDF file",
            description = "Upload a PDF file and extract its text content. Supports PDF files up to 50MB in size."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Text extracted successfully",
                    content = @Content(schema = @Schema(implementation = PdfExtractionResponse.class))),
            @ApiResponse(responseCode = "400", description = "Invalid file format or size",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Extraction failed",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    @PostMapping(value = "/extract", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> extractText(
            @Parameter(description = "PDF file to extract text from (*.pdf, max 50MB)", required = true)
            @RequestParam("file") MultipartFile file) {

        log.info("Received PDF extraction request: {}", file.getOriginalFilename());

        if (!pdfExtractionService.isValidPdfFile(file)) {
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Invalid PDF file")
                            .message("File must be a valid PDF file (*.pdf) and less than 50MB")
                            .path("/api/pdf/extract")
                            .build());
        }

        PdfExtractionResponse response = pdfExtractionService.extractText(file);

        if (!response.isSuccess()) {
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                            .error("Extraction failed")
                            .message("Failed to process PDF file")  // Security: Generic error
                            .path("/api/pdf/extract")
                            .build());
        }

        return ResponseEntity.ok(response);
    }

    @Operation(
            summary = "Extract text from base64-encoded PDF file",
            description = "Send PDF file content as base64-encoded string and extract text. Useful for API integrations where file upload is not available."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Text extracted successfully",
                    content = @Content(schema = @Schema(implementation = PdfExtractionResponse.class))),
            @ApiResponse(responseCode = "400", description = "Invalid request or missing fileContent",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Extraction failed",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    @PostMapping(value = "/extract/base64", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> extractTextFromBase64(
            @Parameter(description = "Extraction request with base64-encoded PDF file content", required = true)
            @Valid @RequestBody PdfExtractionRequest request) {

        log.info("Received base64 PDF extraction request: {}", request.getFilename());

        // Security: Validate base64 content size before processing
        if (request.getFileContent().length() > 70000000) {
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Payload too large")
                            .message("Base64 content exceeds maximum size of 50MB")
                            .path("/api/pdf/extract/base64")
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
                                .path("/api/pdf/extract/base64")
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
                            .path("/api/pdf/extract/base64")
                            .build());
        }

        PdfExtractionResponse response = pdfExtractionService.extractTextFromBase64(
                request.getFileContent(),
                request.getFilename() != null ? request.getFilename() : "unknown.pdf"
        );

        if (!response.isSuccess()) {
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                            .error("Extraction failed")
                            .message("Failed to process PDF file")  // Security: Generic error
                            .path("/api/pdf/extract/base64")
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
                        .path("/api/pdf")
                        .build());
    }
}
