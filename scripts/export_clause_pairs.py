import json
import csv
from pathlib import Path
import tensorflow as tf

# Paths
data_dir = Path("data")
json_path = data_dir / "clause_pairs.json"
csv_path  = data_dir / "clause_pairs.csv"
tfrecord_path = data_dir / "clause_pairs.tfrecord"

# 1. Export JSON → CSV
with open(json_path, "r", encoding="utf-8") as jf, \
     open(csv_path, "w", newline="", encoding="utf-8") as cf:
    entries = json.load(jf)
    writer = csv.DictWriter(cf, fieldnames=["input", "target"])
    writer.writeheader()
    writer.writerows(entries)
print(f"Exported CSV to {csv_path}")

# 2. Export JSON → TFRecord
def _bytes_feature(value: bytes):
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))

with tf.io.TFRecordWriter(str(tfrecord_path)) as writer:
    for entry in entries:
        feature = {
            "input": _bytes_feature(entry["input"].encode("utf-8")),
            "target": _bytes_feature(entry["target"].encode("utf-8")),
        }
        example = tf.train.Example(features=tf.train.Features(feature=feature))
        writer.write(example.SerializeToString())

print(f"Exported TFRecord to {tfrecord_path}")
