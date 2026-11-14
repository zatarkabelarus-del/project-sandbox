<?php
/**
 * Plugin Name: AI Catalog Bridge
 * Description: Lightweight REST API bridge for uploading SEO-optimized multi-format media (WebP, JPEG, AVIF, PNG) without modifying theme templates.
 * Version: 1.1.0
 * Author: AI PicChanger+SEO
 * Requires at least: 5.8
 * Requires PHP: 7.4
 */

if (!defined('ABSPATH')) {
    exit;
}

add_filter('upload_mimes', function ($mimes) {
    $mimes['webp'] = 'image/webp';
    $mimes['avif'] = 'image/avif';
    $mimes['jpg|jpeg|jpe'] = 'image/jpeg';
    $mimes['png'] = 'image/png';
    return $mimes;
});

add_action('rest_api_init', function () {
    register_rest_route('ai-catalog-bridge/v1', '/media', [
        'methods'             => 'POST',
        'callback'            => 'ai_catalog_bridge_upload_media',
        'permission_callback' => 'ai_catalog_bridge_check_permissions',
    ]);
});

/**
 * Гибридная авторизация:
 * 1) Стандартные Application Passwords WordPress (права upload_files)
 * 2) Резервный заголовок X-Bridge-Auth (защита от блокировки Authorization на хостинге)
 */
function ai_catalog_bridge_check_permissions(WP_REST_Request $request) {
    if (is_user_logged_in() && current_user_can('upload_files')) {
        return true;
    }

    $header_token = $request->get_header('X-Bridge-Auth');
    if (!empty($header_token)) {
        $expected_token = defined('AI_CATALOG_BRIDGE_TOKEN')
            ? AI_CATALOG_BRIDGE_TOKEN
            : get_option('ai_catalog_bridge_token', '');

        if (!empty($expected_token) && hash_equals((string) $expected_token, (string) $header_token)) {
            return true;
        }
    }

    return new WP_Error(
        'rest_forbidden',
        'Invalid credentials or missing upload_files capability.',
        ['status' => 403]
    );
}

/**
 * Загрузка изображения (WebP / JPEG / AVIF / PNG) с автоматической привязкой SEO-атрибутов.
 */
function ai_catalog_bridge_upload_media(WP_REST_Request $request) {
    $files = $request->get_file_params();

    if (empty($files['file']) || !empty($files['file']['error'])) {
        return new WP_Error(
            'missing_file',
            'Valid media file is required in "file" field.',
            ['status' => 400]
        );
    }

    require_once ABSPATH . 'wp-admin/includes/file.php';
    require_once ABSPATH . 'wp-admin/includes/media.php';
    require_once ABSPATH . 'wp-admin/includes/image.php';

    $allowed_exts = ['webp', 'jpg', 'jpeg', 'avif', 'png'];
    $alt_text   = sanitize_text_field((string) $request->get_param('alt_text'));
    $title_text = sanitize_text_field((string) $request->get_param('title'));
    $raw_slug   = sanitize_text_field((string) $request->get_param('slug'));

    $file_array = $files['file'];
    $ext = strtolower((string) pathinfo($file_array['name'], PATHINFO_EXTENSION));
    if ($ext === 'jpeg') {
        $ext = 'jpg';
    }
    if (!in_array($ext, $allowed_exts, true)) {
        return new WP_Error(
            'unsupported_format',
            'Allowed formats: webp, jpg, avif, png.',
            ['status' => 415]
        );
    }

    $base_slug = !empty($raw_slug)
        ? sanitize_title($raw_slug)
        : sanitize_title(pathinfo($file_array['name'], PATHINFO_FILENAME));

    if (empty($base_slug)) {
        $base_slug = 'product-slide-' . time();
    }

    $file_array['name'] = $base_slug . '.' . $ext;

    $attachment_id = media_handle_sideload($file_array, 0, $title_text);

    if (is_wp_error($attachment_id)) {
        return new WP_Error(
            'upload_failed',
            $attachment_id->get_error_message(),
            ['status' => 500]
        );
    }

    if (!empty($alt_text)) {
        update_post_meta($attachment_id, '_wp_attachment_image_alt', $alt_text);
    }

    if (!empty($title_text)) {
        wp_update_post([
            'ID'           => $attachment_id,
            'post_title'   => $title_text,
            'post_excerpt' => $alt_text,
        ]);
    }

    return new WP_REST_Response([
        'attachment_id' => (int) $attachment_id,
        'url'           => wp_get_attachment_url($attachment_id),
        'slug'          => get_post_field('post_name', $attachment_id),
        'mime_type'     => get_post_mime_type($attachment_id),
        'alt_text'      => $alt_text,
        'title'         => $title_text,
    ], 201);
}
