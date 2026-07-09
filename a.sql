Table users {
  userId uuid [pk, default: `uuid_generate_v4()`]
  email varchar [unique, not null]
  created_at timestamp [default: `now()`]
}

Table google_accounts {
  id uuid [pk, default: `uuid_generate_v4()`]
  userId uuid [ref: > users.userId]
  gmail_address varchar [not null]
  token_data jsonb [not null, note: 'Lưu nội dung token.json (Nên được mã hóa)']
  is_active boolean [default: true]
  created_at timestamp [default: `now()`]
  updated_at timestamp [default: `now()`]

  indexes {
    (userId, gmail_address) [unique]
  }
}

Table transfer_jobs {
  id uuid [pk, default: `uuid_generate_v4()`]
  source_gmail varchar [not null, ref: > users.email]
  source_folder_id varchar [not null]
  dest_gmail varchar [not null, ref: > users.email]
  status varchar [default: 'pending', note: 'pending, in_progress, completed, failed']
  error_message text
  created_at timestamp [default: `now()`]
  completed_at timestamp
}
