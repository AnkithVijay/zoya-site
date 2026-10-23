-- Product images live in Supabase Storage so adding a product needs no site deploy.
-- Public bucket: files are readable at
--   https://rrsxsqtfotxkjgkbqnpx.supabase.co/storage/v1/object/public/product-images/<product_id>.webp
-- without any storage.objects policy. Deliberately NO policies for anon/authenticated:
-- nobody can list, upload, overwrite or delete through the API except the service role
-- (scripts/add_product.py with SUPABASE_SERVICE_ROLE_KEY).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('product-images', 'product-images', true, 2097152,
        array['image/webp', 'image/png', 'image/jpeg'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;
