Component({
  properties: {
    content: {
      type: String,
      value: '',
      observer: 'parseMarkdown'
    }
  },

  data: {
    nodes: []
  },

  methods: {
    parseMarkdown(markdown) {
      if (!markdown) {
        this.setData({ nodes: [] });
        return;
      }

      const html = this.markdownToHtml(markdown);
      this.setData({ nodes: html });
    },

    markdownToHtml(text) {
      let html = text;

      // 保护代码块
      const codeBlocks = [];
      html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
        const escaped = this.escapeHtml(code);
        const idx = codeBlocks.length;
        codeBlocks.push(`<pre style="background:#f7f8fa;padding:20rpx 24rpx;border-radius:8rpx;margin:20rpx 0;font-size:26rpx;font-family:monospace;white-space:pre-wrap;color:#24292f;border:2rpx solid #e8e8ea;overflow-x:auto;"><code>${escaped}</code></pre>`);
        return `\x00CODE${idx}\x00`;
      });

      // 转义 HTML
      html = this.escapeHtml(html);

      // 表格（必须在换行处理之前）- 改进正则以匹配更多格式
      console.log('[md-render] 原始文本:', html.substring(0, 300));
      html = html.replace(/(\|.+\|)\n(\|[\s:\-|]+\|)\n((?:\|.+\|\n?)+)/g, (match) => {
        console.log('[md-render] 匹配到表格:', match);
        return this.renderTable(match);
      });
      console.log('[md-render] 替换后:', html.substring(0, 300));

      // 标题
      html = html.replace(/^### (.+)$/gm, '<h3 style="font-size:32rpx;font-weight:700;margin:24rpx 0 12rpx;color:#1a1a1a;">$1</h3>');
      html = html.replace(/^## (.+)$/gm, '<h2 style="font-size:34rpx;font-weight:700;margin:28rpx 0 14rpx;color:#1a1a1a;">$1</h2>');
      html = html.replace(/^# (.+)$/gm, '<h1 style="font-size:38rpx;font-weight:700;margin:28rpx 0 14rpx;color:#1a1a1a;">$1</h1>');

      // 粗体
      html = html.replace(/\*\*(.+?)\*\*/g, '<strong style="font-weight:600;color:#1a1a1a;">$1</strong>');
      html = html.replace(/__(.+?)__/g, '<strong style="font-weight:600;color:#1a1a1a;">$1</strong>');

      // 斜体
      html = html.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
      html = html.replace(/_([^_\n]+)_/g, '<em>$1</em>');

      // 行内代码
      html = html.replace(/`([^`]+)`/g, '<code style="background:#f0f0f0;padding:4rpx 8rpx;border-radius:4rpx;font-size:28rpx;font-family:monospace;color:#e83e8c;">$1</code>');

      // 无序列表
      html = html.replace(/^[\-\*\+] (.+)$/gm, '<li style="margin-left:32rpx;margin:2rpx 0;line-height:1.7;list-style-position:inside;">$1</li>');

      // 有序列表
      let counter = 0;
      html = html.replace(/^\d+\. (.+)$/gm, (match, p1) => {
        counter++;
        return `<li style="margin-left:32rpx;margin:2rpx 0;line-height:1.7;list-style-position:inside;">${p1}</li>`;
      });

      // 链接
      html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<span style="color:#5c5cff;text-decoration:underline;">$1</span>');

      // 引用
      html = html.replace(/^&gt; (.+)$/gm, '<blockquote style="border-left:6rpx solid #e8e8ea;padding:12rpx 20rpx;color:#666;margin:16rpx 0;background:#f7f8fa;border-radius:0 8rpx 8rpx 0;">$1</blockquote>');

      // 分隔线
      html = html.replace(/^---+$/gm, '<hr style="border:0;border-top:2rpx solid #e8e8ea;margin:20rpx 0;"/>');

      // 换行
      html = html.replace(/\n\n/g, '<br/><br/>');
      html = html.replace(/\n/g, '<br/>');

      // 恢复代码块
      html = html.replace(/\x00CODE(\d+)\x00/g, (match, idx) => {
        return codeBlocks[parseInt(idx)];
      });

      return `<div style="font-size:30rpx;line-height:1.6;color:#1a1a1a;word-break:break-word;">${html}</div>`;
    },

    renderTable(tableText) {
      const lines = tableText.trim().split('\n').filter(line => line.trim());
      if (lines.length < 3) return tableText;

      let html = '<div style="margin:16rpx 0;border:2rpx solid #d0d0d0;border-radius:8rpx;overflow:hidden;background:#fff;">';

      // 表头
      const headers = lines[0].split('|').map(cell => cell.trim()).filter(cell => cell);
      html += '<div style="display:flex;background:#f0f0f0;border-bottom:2rpx solid #d0d0d0;">';
      headers.forEach((cell, idx) => {
        const borderRight = idx < headers.length - 1 ? 'border-right:2rpx solid #d0d0d0;' : '';
        html += `<div style="flex:1;padding:16rpx;font-weight:600;color:#1a1a1a;font-size:28rpx;${borderRight}text-align:center;">${cell}</div>`;
      });
      html += '</div>';

      // 表体
      for (let i = 2; i < lines.length; i++) {
        const cells = lines[i].split('|').map(cell => cell.trim()).filter(cell => cell);
        if (cells.length === 0) continue;
        
        const borderTop = i > 2 ? 'border-top:2rpx solid #e8e8e8;' : '';
        html += `<div style="display:flex;${borderTop}">`;
        cells.forEach((cell, idx) => {
          const borderRight = idx < cells.length - 1 ? 'border-right:2rpx solid #e8e8e8;' : '';
          html += `<div style="flex:1;padding:16rpx;color:#333;font-size:28rpx;${borderRight}text-align:center;">${cell}</div>`;
        });
        html += '</div>';
      }
      html += '</div>';

      return html;
    },

    escapeHtml(text) {
      return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }
  }
});
