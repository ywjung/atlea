package com.chatbot.document.config;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.TimeUnit;

/**
 * Cache configuration using Caffeine
 * Caches document extraction results to improve performance for repeated requests
 *
 * Performance optimizations:
 * - Increased cache size from 100 to 500 entries
 * - Extended TTL from 1 hour to 2 hours for better hit rate
 * - Statistics enabled for monitoring cache effectiveness
 */
@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager cacheManager = new CaffeineCacheManager("documentExtraction");
        cacheManager.setCaffeine(caffeineCacheBuilder());
        return cacheManager;
    }

    private Caffeine<Object, Object> caffeineCacheBuilder() {
        return Caffeine.newBuilder()
                .maximumSize(500)  // Optimized: Increased from 100 to 500 entries
                .expireAfterWrite(2, TimeUnit.HOURS)  // Optimized: Extended from 1 to 2 hours
                .recordStats();  // Enable statistics for monitoring
    }
}
