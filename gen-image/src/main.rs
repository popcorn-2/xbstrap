mod config;
mod uuid;

use std::{env, fs, io};
use gpt::GptConfig;
use gpt::disk::LogicalBlockSize;
use gpt::mbr::ProtectiveMBR;
use gpt::partition_types::Type;
use ::uuid::Uuid;
use fscommon::StreamSlice;
use std::path::PathBuf;

fn main() {
    let mut args = env::args_os();
    let cfg = args.nth(1).expect("no config file found as first argument");
    let sysroot = args.next().expect("no sysroot found as first argument");

    let config = {
        let config = fs::read_to_string(cfg).expect("failed to read config file");
        serde_yaml::from_str::<config::Config>(&config).expect("failed to parse config file")
    };

    let sysroot = PathBuf::from(sysroot);

    println!("{config:#?}");

    let mut disk_image = fs::File::options()
        .create(true)
        .read(true)
        .write(true)
        .truncate(true)
        .open("popcorn2.img")
        .expect("Could not create disk image");
    
    let total_partition_sizes = config.partitions.iter()
        .map(|(_, info)| info.size)
        .sum::<u64>();
    
    let disk_size = total_partition_sizes + 1024 * 64;
    disk_image.set_len(disk_size).expect("Unable to set disk size");
    
    let mbr = ProtectiveMBR::with_lb_size(
            u32::try_from((disk_size / 512) - 1).unwrap_or(0xFF_FF_FF_FF)
    );
    mbr.overwrite_lba0(&mut disk_image).expect("Failed to write MBR");

    let mut gdisk = GptConfig::new()
                    .writable(true)
                    .logical_block_size(LogicalBlockSize::Lb512)
                    .create_from_device(&mut disk_image, None)
                    .expect("Failed to create GPT disk");
    gdisk.update_partitions(Default::default()).expect("Unable to write GPT partition table");

    gdisk.write_inplace().expect("Unable to write disk image");

    for (name, info) in config.partitions {
        println!("-> Creating partition `{name}`");

        let part_type = if info.type_uuid.len() == 1 { uuid::convert_shortcode(info.type_uuid.chars().next().unwrap()) }
                        else { Type::from(Uuid::parse_str(&info.type_uuid).expect("invalid UUID")) };
        
        let partition_id = gdisk.add_partition(&name, info.size, part_type, 0, None).expect("Unable to create partition");
        let partition = gdisk.partitions().get(&partition_id).unwrap();
        let start_offset = partition.bytes_start(LogicalBlockSize::Lb512).unwrap();
        let end_offset = start_offset + partition.bytes_len(LogicalBlockSize::Lb512).unwrap();

        let mut stream = StreamSlice::new(gdisk.device_mut(), start_offset, end_offset).expect("unable to create stream");

        let source_dir = {
            let path = sysroot.join(info.mountpoint.trim_start_matches('/'));
            fs::read_dir(&path).unwrap_or_else(|_| panic!("failed to open mountpoint at `{}`", path.display()))
        };

        match &*info.partition_type {
            "vfat" => {
                fatfs::format_volume(
                    &mut stream,
                    fatfs::FormatVolumeOptions::new()
                        .fat_type(fatfs::FatType::Fat32),
                ).expect("failed to format partition");

                let fs = fatfs::FileSystem::new(&mut stream, fatfs::FsOptions::new()).expect("failed to open partition");
                let root_dir = fs.root_dir();

                fn process_dir<T: io::Seek + io::Read + io::Write>(dir: fs::ReadDir, cwd: fatfs::Dir<T>) {
                    for entry in dir {
                        let Ok(entry) = entry else { panic!("failed to read directory") };
                    
                        let ty = entry.file_type().unwrap();
                        let path = entry.path();
                        let name = entry.file_name();
                        let name = name.to_str().unwrap();

                        if ty.is_file() {
                            let mut f_dest = cwd.create_file(name).expect("failed to create file");
                            let mut f_source = fs::File::open(path).expect("failed to open source file");
                            std::io::copy(&mut f_source, &mut f_dest);
                        } else if ty.is_dir() {
                            let iter = fs::read_dir(&path).unwrap_or_else(|_| panic!("failed to open directory at `{}`", path.display()));
                            process_dir(iter, cwd.create_dir(name).expect("failed to create dir"));
                        } else {
                            println!("ignoring path of unknown type at `{}`", path.display());
                        }
                    }
                }

                process_dir(source_dir, root_dir);
            },
            part => panic!("unknown partition type `{part}`"),
        }
    }

    gdisk.write_inplace().expect("Unable to write disk image");
}
