package com.chatbot.document.service;

import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.object.content.section_xml.SectionXMLFile;
import kr.dogfoot.hwpxlib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwpxlib.writer.HWPXWriter;
import lombok.extern.slf4j.Slf4j;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

@Slf4j
@Service
public class HtmlToHwpxConversionService {

    /**
     * Convert HTML content to HWPX format
     */
    public byte[] convertHtmlToHwpx(String htmlContent) {
        Path tempFile = null;
        try {
            log.info("Starting HTML to HWPX conversion using hwpxlib");

            // 1. Create a blank HWPX file object
            HWPXFile hwpxFile = BlankFileMaker.make();
            SectionXMLFile section = hwpxFile.sectionXMLFileList().get(0);

            // 2. Parse HTML
            Document doc = Jsoup.parse(htmlContent);

            // 3. Process paragraphs and headings
            processElements(doc.body(), section);

            // 4. Write to temporary file first (hwpxlib requires file-based output for proper ZIP structure)
            tempFile = Files.createTempFile("hwpx_" + UUID.randomUUID(), ".hwpx");
            String tempFilePath = tempFile.toAbsolutePath().toString();

            log.debug("Writing HWPX to temp file: {}", tempFilePath);
            HWPXWriter.toFilepath(hwpxFile, tempFilePath);

            // 5. Read the file back as bytes
            byte[] hwpxBytes = Files.readAllBytes(tempFile);

            log.info("Successfully converted HTML to HWPX ({} bytes)", hwpxBytes.length);
            return hwpxBytes;

        } catch (Exception e) {
            log.error("Failed to convert HTML to HWPX: {}", e.getMessage(), e);
            throw new RuntimeException("HTML to HWPX conversion failed: " + e.getMessage(), e);
        } finally {
            // Clean up temp file
            if (tempFile != null) {
                try {
                    Files.deleteIfExists(tempFile);
                    log.debug("Cleaned up temp file");
                } catch (IOException e) {
                    log.warn("Failed to delete temp file: {}", e.getMessage());
                }
            }
        }
    }

    /**
     * Convert Markdown content to HWPX format
     */
    public byte[] convertMarkdownToHwpx(String markdownContent) {
        try {
            log.info("Starting Markdown to HWPX conversion");

            // Convert Markdown to HTML first
            String htmlContent = convertMarkdownToHtml(markdownContent);

            // Convert HTML to HWPX
            return convertHtmlToHwpx(htmlContent);

        } catch (Exception e) {
            log.error("Failed to convert Markdown to HWPX: {}", e.getMessage(), e);
            throw new RuntimeException("Markdown to HWPX conversion failed: " + e.getMessage(), e);
        }
    }

    /**
     * Process HTML elements and add to section
     */
    private void processElements(Element element, SectionXMLFile section) {
        if (element == null) {
            return;
        }

        for (Element child : element.children()) {
            String tagName = child.tagName().toLowerCase();

            switch (tagName) {
                case "h1", "h2", "h3", "h4", "h5", "h6" -> {
                    String text = child.text().trim();
                    if (!text.isEmpty()) {
                        addParagraph(section, text);
                    }
                }
                case "p" -> {
                    String text = child.text().trim();
                    if (!text.isEmpty()) {
                        addParagraph(section, text);
                    }
                }
                case "ul", "ol" -> {
                    Elements listItems = child.select("li");
                    for (int i = 0; i < listItems.size(); i++) {
                        String text = listItems.get(i).text().trim();
                        if (!text.isEmpty()) {
                            String prefix = tagName.equals("ol") ? (i + 1) + ". " : "• ";
                            addParagraph(section, prefix + text);
                        }
                    }
                }
                case "blockquote" -> {
                    String text = child.text().trim();
                    if (!text.isEmpty()) {
                        addParagraph(section, "> " + text);
                    }
                }
                case "pre", "code" -> {
                    String text = child.text().trim();
                    if (!text.isEmpty()) {
                        for (String line : text.split("\n")) {
                            addParagraph(section, "    " + line);
                        }
                    }
                }
                case "hr" -> addParagraph(section, "─".repeat(50));
                case "br" -> addParagraph(section, "");
                default -> {
                    String text = child.text().trim();
                    if (!text.isEmpty()) {
                        addParagraph(section, text);
                    } else {
                        processElements(child, section);
                    }
                }
            }
        }
    }

    /**
     * Add a paragraph with text to the section
     */
    private void addParagraph(SectionXMLFile section, String text) {
        try {
            section.addNewPara().addNewRun().addNewT().addText(text);
        } catch (Exception e) {
            log.warn("Failed to add paragraph: {}", e.getMessage());
        }
    }

    /**
     * Convert Markdown to HTML (simple implementation)
     */
    private String convertMarkdownToHtml(String markdown) {
        StringBuilder html = new StringBuilder("<html><body>");

        String[] lines = markdown.split("\n");
        boolean inCodeBlock = false;
        boolean inList = false;
        StringBuilder codeBlock = new StringBuilder();

        for (String line : lines) {
            // Code blocks
            if (line.trim().startsWith("```")) {
                if (inCodeBlock) {
                    html.append("<pre>").append(escapeHtml(codeBlock.toString())).append("</pre>");
                    codeBlock.setLength(0);
                    inCodeBlock = false;
                } else {
                    inCodeBlock = true;
                }
                continue;
            }

            if (inCodeBlock) {
                codeBlock.append(line).append("\n");
                continue;
            }

            // Close list if needed
            if (inList && !line.trim().startsWith("- ") && !line.trim().startsWith("* ")
                    && !line.trim().matches("^\\d+\\.\\s.*")) {
                html.append("</ul>");
                inList = false;
            }

            // Headings
            if (line.startsWith("#")) {
                int level = 0;
                while (level < line.length() && line.charAt(level) == '#') {
                    level++;
                }
                if (level <= 6) {
                    String text = line.substring(level).trim();
                    html.append("<h").append(level).append(">")
                            .append(escapeHtml(text))
                            .append("</h").append(level).append(">");
                    continue;
                }
            }

            // Unordered lists
            if (line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
                if (!inList) {
                    html.append("<ul>");
                    inList = true;
                }
                String text = line.trim().substring(2);
                html.append("<li>").append(escapeHtml(text)).append("</li>");
                continue;
            }

            // Ordered lists
            if (line.trim().matches("^\\d+\\.\\s.*")) {
                if (!inList) {
                    html.append("<ol>");
                    inList = true;
                }
                String text = line.trim().replaceFirst("^\\d+\\.\\s+", "");
                html.append("<li>").append(escapeHtml(text)).append("</li>");
                continue;
            }

            // Horizontal rule
            if (line.trim().equals("---") || line.trim().equals("***") || line.trim().equals("___")) {
                html.append("<hr>");
                continue;
            }

            // Blockquote
            if (line.trim().startsWith(">")) {
                String text = line.trim().substring(1).trim();
                html.append("<blockquote>").append(escapeHtml(text)).append("</blockquote>");
                continue;
            }

            // Empty line
            if (line.trim().isEmpty()) {
                html.append("<br>");
                continue;
            }

            // Inline code
            String processedLine = line;
            if (processedLine.contains("`")) {
                processedLine = processedLine.replaceAll("`([^`]+)`", "<code>$1</code>");
            }

            // Bold
            if (processedLine.contains("**")) {
                processedLine = processedLine.replaceAll("\\*\\*([^*]+)\\*\\*", "<strong>$1</strong>");
            }

            // Italic
            if (processedLine.contains("*")) {
                processedLine = processedLine.replaceAll("\\*([^*]+)\\*", "<em>$1</em>");
            }

            // Links
            if (processedLine.contains("[")) {
                processedLine = processedLine.replaceAll("\\[([^]]+)\\]\\(([^)]+)\\)", "<a href=\"$2\">$1</a>");
            }

            // Regular paragraph
            html.append("<p>").append(escapeHtml(processedLine)).append("</p>");
        }

        if (inList) {
            html.append("</ul>");
        }
        if (inCodeBlock) {
            html.append("<pre>").append(escapeHtml(codeBlock.toString())).append("</pre>");
        }

        html.append("</body></html>");
        return html.toString();
    }

    /**
     * Escape HTML special characters
     */
    private String escapeHtml(String text) {
        return text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
