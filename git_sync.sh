#!/bin/bash
# git_sync.sh
# 功能：将当前目录下的 ip.txt 文件强制推送到 GitHub 仓库的 main 分支
# 使用场景：配合 Cloudflare IP 优选工具，自动同步优选结果到远程仓库
#
# ⚠️ 安全提醒：使用前请将下方的 github_token 替换为你自己的 GitHub Personal Access Token
#    切勿将真实令牌提交到公开仓库！

# ==================== GitHub 认证信息（请修改为你的信息） ====================
# 个人访问令牌（Personal Access Token），用于身份验证
# 请设置环境变量 GITHUB_TOKEN 或在下方填写你的 token
# 切勿将真实令牌硬编码在此文件中！
github_token="${GITHUB_TOKEN:-}"
# GitHub 用户名
github_username="JianwenSun"
# 仓库名称
repo_name="cfnb"
# 目标分支
branch="main"

# ==================== 切换到脚本所在目录 ====================
cd "$(dirname "$0")" || exit 1

# ==================== 拉取远程最新更新 ====================
git pull origin "$branch"

# ==================== 暂存并提交 ip.txt ====================
git add ip.txt
commit_msg="Update ip.txt on $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$commit_msg"

# ==================== 强制推送到 GitHub ====================
if [ -z "$github_token" ]; then
    echo "❌ 错误：未设置 GITHUB_TOKEN 环境变量"
    echo "请运行：export GITHUB_TOKEN='your_token_here'"
    exit 1
fi

git push "https://${github_token}@github.com/${github_username}/${repo_name}.git" "$branch" --force

echo "✅ ip.txt 已推送到 GitHub"