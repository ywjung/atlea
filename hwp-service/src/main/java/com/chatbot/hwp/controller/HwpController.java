package com.chatbot.hwp.controller;

import com.chatbot.hwp.model.ErrorResponse;
import com.chatbot.hwp.model.HwpExtractionRequest;
import com.chatbot.hwp.model.HwpExtractionResponse;
import com.chatbot.hwp.service.HwpExtractionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;

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
                            .message(response.getError())
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
            @RequestBody HwpExtractionRequest request) {
        log.info("Received base64 HWP extraction request: {}", request.getFilename());

        if (request.getFileContent() == null || request.getFileContent().isEmpty()) {
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Invalid request")
                            .message("fileContent is required")
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
                            .message(response.getError())
                            .path("/api/hwp/extract/base64")
                            .build());
        }

        return ResponseEntity.ok(response);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleException(Exception e) {
        log.error("Unexpected error: {}", e.getMessage(), e);

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ErrorResponse.builder()
                        .timestamp(LocalDateTime.now())
                        .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                        .error("Internal Server Error")
                        .message(e.getMessage())
                        .path("/api/hwp")
                        .build());
    }
}
