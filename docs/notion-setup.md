# Notion Setup

Create one private Notion page that will hold the recruiting tracker, then share only
that page with your Notion integration. The local bootstrap script creates four private
data sources under it:

- 投递记录
- 流程日志
- 面试记录
- 复习任务

Set these local user environment variables first:

```powershell
[Environment]::SetEnvironmentVariable("NOTION_TOKEN", "<your Notion integration token>", "User")
[Environment]::SetEnvironmentVariable("NOTION_PARENT_PAGE_ID", "<your shared parent page id>", "User")
```

Then run:

```bash
rtk python scripts/notion_bootstrap.py
```

The script writes the generated data source IDs back to local user environment variables:

- `NOTION_APPLICATIONS_DB_ID`
- `NOTION_ACTIVITY_DB_ID`
- `NOTION_INTERVIEWS_DB_ID`
- `NOTION_REVIEW_TASKS_DB_ID`

The `*_DB_ID` names are kept for compatibility, but with the current Notion API they
store data source IDs. Do not paste tokens, page IDs, real job-search records, or Notion
URLs into chat logs or commit them to GitHub.
