#!/usr/bin/env python3
"""AVI Independent Auto Editor v0.3.4 — GUI or CLI."""
import argparse
from autoedit.gui import start_gui
from autoedit.pipeline import process, scan_footage
from autoedit.ai_engine import create_tag_csv


def main():
    parser = argparse.ArgumentParser(description='AVI Independent Auto Editor v0.3.4')
    parser.add_argument('--source', help='Thư mục footage')
    parser.add_argument('--audio', help='File narration')
    parser.add_argument('--output', help='Thư mục xuất rỗng')
    parser.add_argument('--render', action='store_true', help='Xuất final.mp4')
    parser.add_argument('--ai', action='store_true', help='Bật Whisper + CLIP; mặc định CLI là legacy')
    parser.add_argument('--whisper-model', default='small', choices=['tiny','base','small','medium','large-v3'])
    parser.add_argument('--language', default='en', help='en, vi hoặc auto')
    parser.add_argument('--device', default='auto', choices=['cpu','cuda','auto'])
    parser.add_argument('--clip-model', default='openai/clip-vit-base-patch32')
    parser.add_argument('--tags', default=None, help='CSV gắn nhãn người/sự kiện, tùy chọn')
    parser.add_argument('--review-threshold', type=float, default=0.21)
    parser.add_argument('--cache-dir', default=None)
    parser.add_argument('--qwen', action='store_true', help='Bật Qwen mô tả footage + semantic matching')
    parser.add_argument('--qwen-model', default='qwen3-vl:4b-instruct')
    parser.add_argument('--qwen-samples', type=int, default=3)
    parser.add_argument('--analyze-only', action='store_true', help='Chỉ mô tả kho footage bằng Qwen')
    parser.add_argument('--limit', type=int, default=None, help='Chỉ scan N cảnh đầu (test nhanh)')
    parser.add_argument('--make-tags', help='Tạo file CSV mẫu; cần --source')
    parser.add_argument('--seed', type=int, default=404)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--check-hardware', action='store_true', help='Quet GPU, Torch CUDA, Whisper CUDA')
    args = parser.parse_args()
    if args.check_hardware:
        from autoedit.hardware import probe_cuda, describe_hardware
        caps = probe_cuda()
        print(describe_hardware(caps))
        for note in caps['notes']:
            print(note)
        return
    if args.analyze_only:
        if not args.source or not args.output:
            parser.error('--analyze-only cần --source và --output')
        scan_footage(args.source, args.output, qwen_model=args.qwen_model,
                     qwen_samples=args.qwen_samples, limit=args.limit, cache_dir=args.cache_dir)
        return
    if args.make_tags:
        if not args.source:
            parser.error('--make-tags cần --source')
        create_tag_csv(args.source, args.make_tags)
        print('Đã tạo CSV mẫu:', args.make_tags)
        return
    if args.source or args.audio or args.output:
        if not all([args.source, args.audio, args.output]):
            parser.error('Cần đủ --source, --audio và --output')
        process(args.source, args.audio, args.output, render=args.render, seed=args.seed,
                width=args.width, height=args.height, ai_enabled=args.ai,
                whisper_model=args.whisper_model, ai_device=args.device,
                language=args.language, clip_model=args.clip_model,
                tags_file=args.tags, review_threshold=args.review_threshold,
                cache_dir=args.cache_dir, qwen_enabled=args.qwen,
                qwen_model=args.qwen_model, qwen_samples=args.qwen_samples)
    else:
        start_gui()


if __name__ == '__main__':
    main()
