# requirements.txt
# streamlit
# pandas
# plotly

import streamlit as st
import pandas as pd
import plotly.express as px

# ページ設定
st.set_page_config(page_title="FX Trade Analysis v2", layout="wide")

def load_and_process_data(files):
    """
    複数のCSVファイルを読み込み、結合・重複排除してトレードデータを作成する
    """
    if not files:
        return None

    df_list = []
    
    # 1. 各ファイルを読み込む
    for file in files:
        try:
            # デフォルト(UTF-8)で試す
            try:
                df_temp = pd.read_csv(file, dtype=str)
            except UnicodeDecodeError:
                # 失敗したらShift-JISで再試行
                file.seek(0)
                df_temp = pd.read_csv(file, dtype=str, encoding='cp932')
            
            df_list.append(df_temp)
        except Exception as e:
            st.error(f"ファイル {file.name} の読み込み中にエラーが発生しました: {e}")
            return None

    if not df_list:
        return None

    try:
        # 2. 全データを結合
        df_raw = pd.concat(df_list, ignore_index=True)

        # 3. 重複排除 (取引番号をキーにする)
        # '取引番号'がない場合はエラー
        if '取引番号' not in df_raw.columns:
            st.error("CSVに'取引番号'カラムが含まれていません。")
            return None
            
        df_raw.drop_duplicates(subset=['取引番号'], keep='first', inplace=True)

        # 4. 型変換と前処理
        # 金額系: カンマを除去して数値化。'-'などの非数値はNaN→0
        if '決済損益' in df_raw.columns:
            df_raw['決済損益'] = pd.to_numeric(df_raw['決済損益'].str.replace(',', ''), errors='coerce').fillna(0)
        if '数量' in df_raw.columns:
            df_raw['数量'] = pd.to_numeric(df_raw['数量'].str.replace(',', ''), errors='coerce').fillna(0)
        
        # 日時変換
        if '約定日時' in df_raw.columns:
            df_raw['約定日時'] = pd.to_datetime(df_raw['約定日時'])

        # 5. 新規と決済に分割
        df_entry = df_raw[df_raw['区分'] == '新規'].copy()
        df_exit = df_raw[df_raw['区分'] == '決済'].copy()

        # 6. トレードの紐付け (Inner Join)
        merged_df = pd.merge(
            df_exit,
            df_entry,
            left_on='決済対象取引番号',
            right_on='取引番号',
            suffixes=('_exit', '_entry'),
            how='inner'
        )

        # 7. 計算カラムの作成
        merged_df['holding_time'] = merged_df['約定日時_exit'] - merged_df['約定日時_entry']
        merged_df['profit'] = merged_df['決済損益_exit'] # 決済行の損益を採用
        
        # 月カラム
        merged_df['month'] = merged_df['約定日時_exit'].dt.strftime('%Y-%m')
        
        # 表示用に整理
        merged_df['pair'] = merged_df['通貨ペア_entry']
        merged_df['side'] = merged_df['売買_entry']

        return merged_df.sort_values('約定日時_exit')

    except Exception as e:
        st.error(f"データ処理中にエラーが発生しました: {e}")
        return None

def calculate_kpis(df):
    """
    データフレームからKPIを計算する
    """
    if len(df) == 0:
        return None

    # 勝率
    win_trades = df[df['profit'] > 0]
    loss_trades = df[df['profit'] < 0]
    total_trades = len(df)
    
    win_rate = (len(win_trades) / total_trades) * 100 if total_trades > 0 else 0

    # リスクリワードレシオ
    avg_profit = win_trades['profit'].mean() if len(win_trades) > 0 else 0
    avg_loss = loss_trades['profit'].mean() if len(loss_trades) > 0 else 0
    
    if avg_loss == 0:
        risk_reward = float('inf')
    else:
        risk_reward = avg_profit / abs(avg_loss)

    # 最大ドローダウン
    df_sorted = df.sort_values('約定日時_exit')
    cumulative_profit = df_sorted['profit'].cumsum()
    running_max = cumulative_profit.cummax()
    drawdown = cumulative_profit - running_max
    max_drawdown = drawdown.min()

    # 平均保有時間
    avg_holding_time = df['holding_time'].mean()

    # 合計損益
    total_profit = df['profit'].sum()

    return {
        "win_rate": win_rate,
        "risk_reward": risk_reward,
        "max_drawdown": max_drawdown,
        "avg_holding_time": avg_holding_time,
        "total_profit": total_profit
    }

def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == "fx2025": # パスワードはここで設定
            st.session_state["password_correct"] = True
            # パスワード入力フィールドをリセットしない（リセットすると再実行で状態が消えることがあるため）
            del st.session_state["password"] 
        else:
            st.session_state["password_correct"] = False

    # 初回起動時やリロード時の初期化
    if "password_correct" not in st.session_state:
        # パスワード入力フォームを表示
        st.text_input(
            "パスワードを入力してください", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # パスワードが間違っていた場合
        st.text_input(
            "パスワードを入力してください", type="password", on_change=password_entered, key="password"
        )
        st.error("パスワードが違います")
        return False
    else:
        # 正しいパスワードが入力されている
        return True

def main():
    # パスワードチェック
    if not check_password():
        st.stop() # パスワードが通るまで以下の処理を止める

    st.sidebar.header("Data Upload")
    
    # 複数ファイル対応: accept_multiple_files=True
    uploaded_files = st.sidebar.file_uploader(
        "CSVファイルをアップロード (複数可)", 
        type=['csv'], 
        accept_multiple_files=True
    )

    if uploaded_files:
        df = load_and_process_data(uploaded_files)
        
        if df is not None and not df.empty:
            # データ期間の表示
            min_date = df['約定日時_exit'].min()
            max_date = df['約定日時_exit'].max()
            st.sidebar.markdown("---")
            st.sidebar.markdown(f"**データ期間**")
            st.sidebar.text(f"{min_date.strftime('%Y/%m/%d')} \n   〜 {max_date.strftime('%Y/%m/%d')}")
            st.sidebar.markdown("---")

            # サイドバー: 月選択
            months = sorted(df['month'].unique(), reverse=True)
            selected_month = st.sidebar.selectbox("対象月を選択", months, index=0)
            
            # データフィルタリング
            filtered_df = df[df['month'] == selected_month].copy()
            
            # メインエリア表示
            st.title(f"{selected_month} トレード分析")

            # KPI計算
            kpis = calculate_kpis(filtered_df)
            
            if kpis:
                # KPI表示
                col1, col2, col3, col4, col5 = st.columns(5)
                
                col1.metric("勝率", f"{kpis['win_rate']:.1f}%")
                
                rr_display = "Inf" if kpis['risk_reward'] == float('inf') else f"{kpis['risk_reward']:.2f}"
                col2.metric("リスクリワード", rr_display)
                
                col3.metric("最大ドローダウン", f"¥{kpis['max_drawdown']:,.0f}")
                
                hours = kpis['avg_holding_time'].seconds // 3600
                minutes = (kpis['avg_holding_time'].seconds % 3600) // 60
                col4.metric("平均保有時間", f"{hours}h {minutes}m")
                
                profit_color = "green" if kpis['total_profit'] >= 0 else "red"
                col5.markdown(f"""
                <div style="text-align: center;">
                    <p style="font-size: 14px; margin-bottom: 0;">合計損益</p>
                    <p style="font-size: 24px; font-weight: bold; color: {profit_color};">
                        ¥{kpis['total_profit']:,.0f}
                    </p>
                </div>
                """, unsafe_allow_html=True)

                # グラフエリア
                st.markdown("### 月次損益推移 (累積)")
                filtered_df = filtered_df.sort_values('約定日時_exit')
                filtered_df['cumulative_profit'] = filtered_df['profit'].cumsum()

                fig = px.area(
                    filtered_df, 
                    x='約定日時_exit', 
                    y='cumulative_profit',
                    labels={'約定日時_exit': '日時', 'cumulative_profit': '累積損益'},
                    markers=True
                )
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                fig.update_traces(
                    hovertemplate='<b>日時</b>: %{x}<br><b>累積損益</b>: ¥%{y:,.0f}<br><b>損益</b>: ¥%{customdata:,.0f}',
                    customdata=filtered_df['profit']
                )
                st.plotly_chart(fig, use_container_width=True)

                # データテーブル
                st.markdown("### トレード一覧")
                table_df = filtered_df.copy()
                table_df['数量'] = table_df['数量_exit']
                
                column_config = {
                    '約定日時_exit': '決済日時',
                    '約定日時_entry': '新規日時',
                    'holding_time': '保有時間',
                    'pair': '通貨ペア',
                    'side': '売買',
                    '数量': '数量',
                    'profit': '損益'
                }
                
                final_table = table_df[['約定日時_exit', '約定日時_entry', 'holding_time', 'pair', 'side', '数量', 'profit']]
                final_table.columns = [column_config[c] for c in final_table.columns]

                def color_profit(val):
                    color = '#d4edda' if val > 0 else '#f8d7da' if val < 0 else ''
                    text_color = '#155724' if val > 0 else '#721c24' if val < 0 else ''
                    return f'background-color: {color}; color: {text_color}'

                st.dataframe(
                    final_table.style.map(color_profit, subset=['損益'])
                                     .format({'損益': '¥{:,.0f}', '数量': '{:,.0f}'}),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("データ件数が0件です。")
    else:
        st.info("左側のサイドバーからCSVファイルをアップロードしてください（複数選択可）。")

if __name__ == "__main__":
    main()
