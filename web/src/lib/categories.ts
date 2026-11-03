// arXiv 分类的中文名（只在界面上用）
const NAMES: Record<string, string> = {
  'cs.AI': '人工智能',
  'cs.CV': '计算机视觉',
  'cs.CL': '计算语言学',
  'cs.LG': '机器学习',
  'cs.RO': '机器人学',
  'cs.NE': '神经与进化计算',
  'cs.IR': '信息检索',
  'cs.HC': '人机交互',
  'cs.CR': '密码学与安全',
  'cs.DC': '分布式计算',
  'cs.SE': '软件工程',
  'cs.SY': '系统与控制',
  'eess.SY': '系统与控制',
  'stat.ML': '统计机器学习'
}

export const categoryName = (code: string): string => NAMES[code] ?? ''
export const anchorOf = (code: string): string => `cat-${code.replace('.', '-')}`
