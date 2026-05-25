use serde::Deserialize;
use std::collections::HashMap;

// The root config structure
#[derive(Debug, Deserialize)]
pub struct Config {
    pub partitions: HashMap<String, PartitionConfig>,
}

// The structure for individual partition entries
#[derive(Debug, Deserialize)]
pub struct PartitionConfig {
    #[serde(rename = "type")] 
    pub partition_type: String,
    pub mountpoint: String,
    pub type_uuid: String,
    pub size: u64,
}
