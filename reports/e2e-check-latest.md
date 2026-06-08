# E2E 测试报告

- 生成时间: `2026-06-04T18:31:25+08:00`
- 测试视频: `D:\work\video\妹妹的情改十年归来夺我产（已完成）\videos\十年归来夺我产 - 第2集.mp4`

## 结果汇总

| 平台 | 状态 | 通过步骤 | 总步骤 | 耗时 |
|---|---|---|---|---|
| 小红书 (`xiaohongshu`) | **✓ PASS** | 9/9 | 9 | 211.4s |

## 详细结果

### 小红书 (`xiaohongshu`) — ✓ PASS

| # | 步骤 | 状态 | 耗时 | 说明 |
|---|---|---|---|---|
| 1 | verify_cookie | ✓ | 7.5s |  |
| 2 | goto_upload_page | ✓ | 0.5s |  |
| 3 | upload_video_file | ✓ | 1.0s |  |
| 4 | wait_for_upload_complete | ✓ | 62.6s |  |
| 5 | fill_video_info | ✓ | 0.1s |  |
| 6 | set_thumbnail | ✓ | — |  |
| 7 | verify_publish_button | ✓ | 0.0s |  |
| 8 | upload_video | ✓ | 64.3s |  |
| 9 | upload_video_flow | ✓ | 75.3s |  |

## 测试说明

- **✓ PASS**: 所有步骤通过（`verify_publish_button` 仅检查按钮存在，不点击）
- **✗ FAIL**: 任一步骤失败
- **— 跳过**: 无 cookie 文件，未执行测试
- 本测试**不会实际发布**内容，发布按钮仅做可见性验证
