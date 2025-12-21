package com.chatbot.hwp.model;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
@Schema(description = "Request body for extracting text from base64-encoded PDF file")
public class PdfExtractionRequest {

    @Schema(
            description = "Base64-encoded content of the PDF file",
            example = "JVBERi0xLjcKJe...",
            required = true
    )
    @NotNull(message = "File content is required")
    @Size(max = 70000000, message = "Base64 content exceeds maximum size (50MB encoded)")
    private String fileContent;

    @Schema(
            description = "Original filename of the PDF file (optional, used for logging)",
            example = "document.pdf",
            required = false
    )
    @Pattern(
            regexp = "^[a-zA-Z0-9가-힣._-]{1,255}\\.pdf$",
            message = "Filename must be alphanumeric with .pdf extension, max 255 chars"
    )
    @Size(max = 255, message = "Filename too long")
    private String filename;

    /**
     * Security: Sanitize filename to prevent path traversal and log injection
     */
    public void setFilename(String filename) {
        if (filename != null && !filename.isEmpty()) {
            // Remove path separators and control characters
            this.filename = filename.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1F]", "_")
                                   .replaceAll("\\.{2,}", ".")  // Prevent ..
                                   .substring(0, Math.min(filename.length(), 255));
        } else {
            this.filename = "unknown.pdf";
        }
    }
}
