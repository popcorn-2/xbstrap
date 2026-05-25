pub fn convert_shortcode(short: char) -> gpt::partition_types::Type {
    match short {
        'U' => gpt::partition_types::Type::from_name("efi").unwrap(),
        _ => panic!("unknown partition shortcode `{short}`"),
    }
}
