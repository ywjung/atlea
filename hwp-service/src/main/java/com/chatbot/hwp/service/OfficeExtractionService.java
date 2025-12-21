package com.chatbot.hwp.service;

import com.chatbot.hwp.model.DocumentExtractionResponse;
import lombok.extern.slf4j.Slf4j;
import org.apache.poi.hslf.usermodel.*;
import org.apache.poi.hwpf.HWPFDocument;
import org.apache.poi.hwpf.extractor.WordExtractor;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xslf.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.*;

@Slf4j
@Service
public class OfficeExtractionService {

    private static final long MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
    private static final List<String> WORD_EXTENSIONS = List.of(".doc", ".docx");
    private static final List<String> EXCEL_EXTENSIONS = List.of(".xls", ".xlsx");
    private static final List<String> POWERPOINT_EXTENSIONS = List.of(".ppt", ".pptx");

    /**
     * Validate if the file is a valid Office document
     */
    public boolean isValidOfficeFile(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            log.warn("File is null or empty");
            return false;
        }

        // Check file size
        if (file.getSize() > MAX_FILE_SIZE) {
            log.warn("File size exceeds limit: {} bytes", file.getSize());
            return false;
        }

        // Check file extension
        String originalFilename = file.getOriginalFilename();
        if (originalFilename == null) {
            log.warn("Filename is null");
            return false;
        }

        String lowerFilename = originalFilename.toLowerCase();
        boolean hasValidExtension = WORD_EXTENSIONS.stream().anyMatch(lowerFilename::endsWith) ||
                                    EXCEL_EXTENSIONS.stream().anyMatch(lowerFilename::endsWith) ||
                                    POWERPOINT_EXTENSIONS.stream().anyMatch(lowerFilename::endsWith);

        if (!hasValidExtension) {
            log.warn("Invalid file extension: {}", originalFilename);
            return false;
        }

        return true;
    }

    /**
     * Extract text from Office file (Word, Excel, PowerPoint)
     */
    public DocumentExtractionResponse extractText(MultipartFile file) {
        long startTime = System.currentTimeMillis();
        String filename = file.getOriginalFilename();

        try {
            log.info("Extracting text from Office file: {}", filename);
            byte[] fileBytes = file.getBytes();

            return extractTextFromBytes(fileBytes, filename, startTime);
        } catch (IOException e) {
            log.error("Failed to read file bytes: {}", e.getMessage());
            return buildErrorResponse(filename, "Failed to read file", startTime);
        }
    }

    /**
     * Extract text from base64-encoded Office file
     */
    public DocumentExtractionResponse extractTextFromBase64(String base64Content, String filename) {
        long startTime = System.currentTimeMillis();

        try {
            log.info("Extracting text from base64 Office file: {}", filename);
            byte[] fileBytes = Base64.getDecoder().decode(base64Content);

            return extractTextFromBytes(fileBytes, filename, startTime);
        } catch (IllegalArgumentException e) {
            log.error("Invalid base64 encoding: {}", e.getMessage());
            return buildErrorResponse(filename, "Invalid base64 encoding", startTime);
        }
    }

    /**
     * Core extraction logic from byte array
     */
    private DocumentExtractionResponse extractTextFromBytes(byte[] fileBytes, String filename,
                                                            long startTime) {
        try {
            String text;
            String fileType;

            if (filename.toLowerCase().endsWith(".docx")) {
                text = extractFromDocx(fileBytes);
                fileType = "DOCX";
            } else if (filename.toLowerCase().endsWith(".doc")) {
                text = extractFromDoc(fileBytes);
                fileType = "DOC";
            } else if (filename.toLowerCase().endsWith(".xlsx")) {
                text = extractFromXlsx(fileBytes);
                fileType = "XLSX";
            } else if (filename.toLowerCase().endsWith(".xls")) {
                text = extractFromXls(fileBytes);
                fileType = "XLS";
            } else if (filename.toLowerCase().endsWith(".pptx")) {
                text = extractFromPptx(fileBytes);
                fileType = "PPTX";
            } else if (filename.toLowerCase().endsWith(".ppt")) {
                text = extractFromPpt(fileBytes);
                fileType = "PPT";
            } else {
                throw new IllegalArgumentException("Unsupported file format: " + filename);
            }

            long processingTime = System.currentTimeMillis() - startTime;

            log.info("Successfully extracted {} characters from {} ({}) in {}ms",
                    text.length(), filename, fileType, processingTime);

            return DocumentExtractionResponse.builder()
                    .text(text)
                    .success(true)
                    .filename(filename)
                    .fileType(fileType)
                    .processingTimeMs(processingTime)
                    .build();
        } catch (Exception e) {
            log.error("Failed to extract text from Office file: {}", e.getMessage());
            return buildErrorResponse(filename, "Office extraction failed", startTime);
        }
    }

    /**
     * Extract text from DOCX (Word 2007+)
     */
    private String extractFromDocx(byte[] fileBytes) throws IOException {
        try (XWPFDocument document = new XWPFDocument(new ByteArrayInputStream(fileBytes))) {
            StringBuilder text = new StringBuilder();

            for (XWPFParagraph paragraph : document.getParagraphs()) {
                String paraText = paragraph.getText();
                if (paraText != null && !paraText.trim().isEmpty()) {
                    text.append(paraText).append("\n");
                }
            }

            return text.toString();
        }
    }

    /**
     * Extract text from DOC (Word 97-2003)
     */
    private String extractFromDoc(byte[] fileBytes) throws IOException {
        try (HWPFDocument document = new HWPFDocument(new ByteArrayInputStream(fileBytes));
             WordExtractor extractor = new WordExtractor(document)) {
            return extractor.getText();
        }
    }

    /**
     * Extract text from XLSX (Excel 2007+)
     */
    private String extractFromXlsx(byte[] fileBytes) throws IOException {
        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(fileBytes))) {
            return extractTextFromWorkbook(workbook);
        }
    }

    /**
     * Extract text from XLS (Excel 97-2003)
     */
    private String extractFromXls(byte[] fileBytes) throws IOException {
        try (HSSFWorkbook workbook = new HSSFWorkbook(new ByteArrayInputStream(fileBytes))) {
            return extractTextFromWorkbook(workbook);
        }
    }

    /**
     * Extract text from Excel workbook (common logic for XLS and XLSX)
     */
    private String extractTextFromWorkbook(Workbook workbook) {
        StringBuilder text = new StringBuilder();
        DataFormatter formatter = new DataFormatter();

        for (int i = 0; i < workbook.getNumberOfSheets(); i++) {
            Sheet sheet = workbook.getSheetAt(i);
            text.append("Sheet: ").append(sheet.getSheetName()).append("\n\n");

            for (Row row : sheet) {
                for (Cell cell : row) {
                    String cellValue = formatter.formatCellValue(cell);
                    if (cellValue != null && !cellValue.trim().isEmpty()) {
                        text.append(cellValue).append("\t");
                    }
                }
                text.append("\n");
            }
            text.append("\n");
        }

        return text.toString();
    }

    /**
     * Extract text from PPTX (PowerPoint 2007+)
     */
    private String extractFromPptx(byte[] fileBytes) throws IOException {
        try (XMLSlideShow ppt = new XMLSlideShow(new ByteArrayInputStream(fileBytes))) {
            StringBuilder text = new StringBuilder();

            int slideNumber = 1;
            for (XSLFSlide slide : ppt.getSlides()) {
                text.append("Slide ").append(slideNumber++).append(":\n");

                for (XSLFShape shape : slide.getShapes()) {
                    if (shape instanceof XSLFTextShape) {
                        XSLFTextShape textShape = (XSLFTextShape) shape;
                        String shapeText = textShape.getText();
                        if (shapeText != null && !shapeText.trim().isEmpty()) {
                            text.append(shapeText).append("\n");
                        }
                    }
                }
                text.append("\n");
            }

            return text.toString();
        }
    }

    /**
     * Extract text from PPT (PowerPoint 97-2003)
     */
    private String extractFromPpt(byte[] fileBytes) throws IOException {
        try (HSLFSlideShow ppt = new HSLFSlideShow(new ByteArrayInputStream(fileBytes))) {
            StringBuilder text = new StringBuilder();

            int slideNumber = 1;
            for (HSLFSlide slide : ppt.getSlides()) {
                text.append("Slide ").append(slideNumber++).append(":\n");

                for (HSLFShape shape : slide.getShapes()) {
                    if (shape instanceof HSLFTextShape) {
                        HSLFTextShape textShape = (HSLFTextShape) shape;
                        String shapeText = textShape.getText();
                        if (shapeText != null && !shapeText.trim().isEmpty()) {
                            text.append(shapeText).append("\n");
                        }
                    }
                }
                text.append("\n");
            }

            return text.toString();
        }
    }

    /**
     * Build error response
     */
    private DocumentExtractionResponse buildErrorResponse(String filename, String errorMessage, long startTime) {
        return DocumentExtractionResponse.builder()
                .text("")
                .success(false)
                .error(errorMessage)
                .filename(filename)
                .fileType("UNKNOWN")
                .processingTimeMs(System.currentTimeMillis() - startTime)
                .build();
    }
}
