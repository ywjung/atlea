package com.chatbot.hwp.model;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "Response containing extracted text and metadata from PDF file")
public class PdfExtractionResponse {

    @Schema(description = "Extracted full text content from the PDF file", example = "Chapter 1\\n\\nIntroduction...")
    private String text;

    @Schema(description = "Text chunks for vector storage (if chunking enabled)")
    private List<TextChunk> chunks;

    @Schema(description = "Total number of pages in the PDF", example = "42")
    private int pageCount;

    @Schema(description = "Whether the extraction was successful", example = "true")
    private boolean success;

    @Schema(description = "Error message if extraction failed (null if successful)")
    private String error;

    @Schema(description = "Original filename of the processed PDF file", example = "document.pdf")
    private String filename;

    @Schema(description = "Time taken to process the file in milliseconds", example = "235")
    private long processingTimeMs;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @Schema(description = "Text chunk with metadata for vector storage")
    public static class TextChunk {
        @Schema(description = "Chunk text content", example = "This is a sample text chunk...")
        private String text;

        @Schema(description = "Chunk index in the document", example = "0")
        private int chunkIndex;

        @Schema(description = "Total number of chunks", example = "15")
        private int totalChunks;

        @Schema(description = "Source filename", example = "document.pdf")
        private String filename;

        @Schema(description = "Page numbers included in this chunk", example = "[1, 2]")
        private List<Integer> pageNumbers;
    }
}
