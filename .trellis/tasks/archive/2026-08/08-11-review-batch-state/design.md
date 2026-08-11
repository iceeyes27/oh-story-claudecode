# 设计

- 状态工具独占 `.story-review/latest.json`；故事内容与 `追踪/` 权威文件不受影响。
- full/lean 使用 revision 申领、二次校验和原子替换；solo/显式只读只读。
- claim_id 限定释放权限；活动 review、异常状态和输入变化均显式处理。
