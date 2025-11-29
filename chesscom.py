"""
Chess.com Performance Dashboard
================================
Displays your chess.com stats in an interactive browser dashboard.

WINDOWS SETUP (VSCode):
1. Open VSCode terminal (Ctrl + `)
2. Install dependencies:
   pip install flask pandas plotly requests
3. Run the script:
   python chess_dashboard.py
4. Browser will auto-open to http://127.0.0.1:5000/
5. Press Ctrl+C in terminal to stop the server

Configure your username and start date below.
"""

import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from flask import Flask, render_template_string
import webbrowser
from threading import Timer

# --- USER CONFIGURATION ---
USERNAME = "kxrook"       # Replace with your username
START_DATE = "2025-11-01" # Format: YYYY-MM-DD
GAME_INTERVAL = 10        # For the 2nd chart: Average rating every N games

# --- HELPER FUNCTIONS ---
def get_headers():
    return {'User-Agent': 'VSCodeChessDashboard/4.0'}

def get_data(url):
    try:
        response = requests.get(url, headers=get_headers())
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

def process_all_modes(username, start_date_str):
    """Fetches games from a specific date onwards"""
    try:
        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
        start_timestamp = start_dt.timestamp()
    except ValueError:
        print("❌ Error: Date format must be YYYY-MM-DD")
        return pd.DataFrame()

    archives = get_data(f"https://api.chess.com/pub/player/{username}/games/archives")
    if not archives: return pd.DataFrame()

    all_archives = archives.get('archives', [])
    relevant_archives = []

    print(f"🔍 Filtering archives starting from {start_date_str}...")

    for url in all_archives:
        parts = url.split('/')
        year = int(parts[-2])
        month = int(parts[-1])

        if (year > start_dt.year) or (year == start_dt.year and month >= start_dt.month):
            relevant_archives.append(url)

    print(f"📥 Downloading games from {len(relevant_archives)} month(s)...")

    history_data = []

    for url in relevant_archives:
        data = get_data(url)
        if not data: continue

        for game in data.get('games', []):
            if game['end_time'] < start_timestamp:
                continue

            time_class = game.get('time_class')
            rules = game.get('rules', 'chess')
            is_960 = (rules == 'chess960')

            if time_class in ['rapid', 'blitz', 'bullet', 'daily']:
                if game['white']['username'].lower() == username.lower():
                    user_color = 'white'
                else:
                    user_color = 'black'

                rating = game[user_color]['rating']
                end_time = datetime.fromtimestamp(game['end_time'])

                game_result = game[user_color]['result']
                game_status = 'Draw'
                if game_result in ['win', 'agreed', 'repetition', 'stalemate', 'insufficient_material', '50move', 'timevsinsufficientmaterial']:
                    if game_result == 'win':
                        game_status = 'Win'
                    else:
                        game_status = 'Draw'
                elif game_result in ['checkmated', 'resigned', 'timeout', 'abandoned']:
                    game_status = 'Loss'

                # Determine mode with 960 suffix if applicable
                mode_name = time_class.capitalize()
                if is_960:
                    mode_name = f"{mode_name}960"

                history_data.append({
                    'Date': end_time,
                    'Rating': rating,
                    'Mode': mode_name,
                    'Status': game_status,
                    'Is960': is_960
                })

    return pd.DataFrame(history_data)

# --- CHART GENERATION ---
def create_overall_performance_chart(df):
    """Chart: Overall performance across all game modes - stacked bar showing wins vs losses/draws"""
    if df.empty:
        return "<p>No games found.</p>"
    
    df_copy = df.copy()
    df_copy['DateOnly'] = df_copy['Date'].dt.date
    df_copy['DateOnly'] = pd.to_datetime(df_copy['DateOnly'])
    
    # Calculate daily totals
    daily_stats = df_copy.groupby('DateOnly').agg({
        'Status': lambda x: [(x == 'Win').sum(), (x != 'Win').sum()]
    }).reset_index()
    
    # Expand the Status column into separate columns
    daily_stats['Wins'] = daily_stats['Status'].apply(lambda x: x[0])
    daily_stats['NonWins'] = daily_stats['Status'].apply(lambda x: x[1])
    daily_stats['TotalGames'] = daily_stats['Wins'] + daily_stats['NonWins']
    daily_stats['WinPct'] = (daily_stats['Wins'] / daily_stats['TotalGames'] * 100).round(1)
    
    # Create stacked bar chart
    fig = go.Figure()
    
    # Add wins bar (green)
    fig.add_trace(go.Bar(
        x=daily_stats['DateOnly'],
        y=daily_stats['Wins'],
        name='Wins',
        marker_color='#76b900',
        hovertemplate='<b>%{x}</b><br>Wins: %{y}<extra></extra>'
    ))
    
    # Add losses/draws bar (red)
    fig.add_trace(go.Bar(
        x=daily_stats['DateOnly'],
        y=daily_stats['NonWins'],
        name='Losses/Draws',
        marker_color='#ca3431',
        hovertemplate='<b>%{x}</b><br>Losses/Draws: %{y}<extra></extra>'
    ))
    
    # Update layout for stacked bars
    fig.update_layout(
        title=f'Overall Performance - All Game Modes (Since {START_DATE})',
        template='plotly_dark',
        xaxis=dict(title='Date'),
        yaxis=dict(title='Games Played'),
        barmode='stack',
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1
        ),
        height=450
    )
    
    return fig.to_html(full_html=False, include_plotlyjs='cdn')

def create_daily_games_chart(df, is_960=False):
    """Chart: Total games played by day"""
    # Filter for 960 or standard games
    filtered_df = df[df['Is960'] == is_960].copy()
    
    if filtered_df.empty:
        return "<p>No games found for this variant.</p>"
    
    filtered_df['DateOnly'] = filtered_df['Date'].dt.date
    
    # Count games per day per mode
    daily_counts = filtered_df.groupby(['DateOnly', 'Mode']).size().reset_index(name='Games')
    daily_counts['DateOnly'] = pd.to_datetime(daily_counts['DateOnly'])
    
    # Remove '960' suffix from mode names for consistent coloring
    mode_map = {
        'Rapid960': 'Rapid', 'Blitz960': 'Blitz', 
        'Bullet960': 'Bullet', 'Daily960': 'Daily',
        'Rapid': 'Rapid', 'Blitz': 'Blitz',
        'Bullet': 'Bullet', 'Daily': 'Daily'
    }
    daily_counts['ModeColor'] = daily_counts['Mode'].map(mode_map)
    
    title = f'Total Games Played by Day - Chess 960 (Since {START_DATE})' if is_960 else f'Total Games Played by Day - Standard Chess (Since {START_DATE})'
    
    fig = px.bar(daily_counts, x='DateOnly', y='Games', color='ModeColor',
                  title=title,
                  template='plotly_dark',
                  color_discrete_map={'Rapid': '#76b900', 'Blitz': '#F0C800', 'Bullet': '#ca3431', 'Daily': '#00BFFF'},
                  labels={'DateOnly': 'Date', 'Games': 'Games Played'})
    
    # Update hover data to show actual mode name
    for i, trace in enumerate(fig.data):
        mode_color = trace.name
        actual_modes = daily_counts[daily_counts['ModeColor'] == mode_color]['Mode'].unique()
        if len(actual_modes) > 0:
            trace.name = actual_modes[0]
    
    fig.update_layout(hovermode='x unified', barmode='stack')
    
    return fig.to_html(full_html=False, include_plotlyjs='cdn')

def create_daily_average_chart(df, is_960=False):
    """Chart 1: Average ELO by day and time mode"""
    # Filter for 960 or standard games
    filtered_df = df[df['Is960'] == is_960].copy()
    
    if filtered_df.empty:
        return "<p>No games found for this variant.</p>"
    
    filtered_df['DateOnly'] = filtered_df['Date'].dt.date
    
    daily_avg = filtered_df.groupby(['DateOnly', 'Mode'])['Rating'].mean().reset_index()
    daily_avg['DateOnly'] = pd.to_datetime(daily_avg['DateOnly'])
    
    # Remove '960' suffix from mode names for consistent coloring
    mode_map = {
        'Rapid960': 'Rapid', 'Blitz960': 'Blitz', 
        'Bullet960': 'Bullet', 'Daily960': 'Daily',
        'Rapid': 'Rapid', 'Blitz': 'Blitz',
        'Bullet': 'Bullet', 'Daily': 'Daily'
    }
    daily_avg['ModeColor'] = daily_avg['Mode'].map(mode_map)
    
    title = f'Average ELO by Day - Chess 960 (Since {START_DATE})' if is_960 else f'Average ELO by Day - Standard Chess (Since {START_DATE})'
    
    fig = px.line(daily_avg, x='DateOnly', y='Rating', color='ModeColor',
                  title=title,
                  template='plotly_dark',
                  color_discrete_map={'Rapid': '#76b900', 'Blitz': '#F0C800', 'Bullet': '#ca3431', 'Daily': '#00BFFF'},
                  labels={'DateOnly': 'Date', 'Rating': 'Average Rating'})
    
    # Update hover data to show actual mode name
    for i, trace in enumerate(fig.data):
        mode_color = trace.name
        actual_modes = daily_avg[daily_avg['ModeColor'] == mode_color]['Mode'].unique()
        if len(actual_modes) > 0:
            trace.name = actual_modes[0]
    
    fig.update_traces(mode='lines+markers')
    fig.update_layout(hovermode='x unified')
    
    return fig.to_html(full_html=False, include_plotlyjs='cdn')

def create_interval_table(df, is_960=False):
    """Chart 2: Table showing average ELO and win % at every N-game interval"""
    # Filter for 960 or standard games
    filtered_df = df[df['Is960'] == is_960].copy()
    
    if filtered_df.empty:
        return "<p>No games found for this variant.</p>"
    
    # Add game count per mode
    filtered_df = filtered_df.sort_values(['Mode', 'Date'])
    filtered_df['GameCount'] = filtered_df.groupby('Mode').cumcount() + 1
    
    # Filter to interval milestones
    df_intervals = filtered_df[filtered_df['GameCount'] % GAME_INTERVAL == 0].copy()
    
    if df_intervals.empty:
        return "<p>Not enough games to show intervals yet.</p>"
    
    # Calculate average rating and win percentage at each interval
    interval_stats = []
    for mode in filtered_df['Mode'].unique():
        mode_data = filtered_df[filtered_df['Mode'] == mode]
        for game_count in range(GAME_INTERVAL, len(mode_data) + 1, GAME_INTERVAL):
            # Get games up to this point
            games_up_to_interval = mode_data.iloc[:game_count]
            avg_rating = games_up_to_interval['Rating'].mean()
            wins = len(games_up_to_interval[games_up_to_interval['Status'] == 'Win'])
            win_pct = (wins / game_count * 100)
            
            interval_stats.append({
                'Mode': mode,
                'Games Played': game_count,
                'Average Rating': int(round(avg_rating)),
                'Win %': win_pct
            })
    
    interval_df = pd.DataFrame(interval_stats)
    
    # Create pivot table for ratings with win percentage
    pivot_data = {}
    pivot_data['Games Played'] = sorted(interval_df['Games Played'].unique())
    
    mode_list = ['Blitz960', 'Bullet960', 'Rapid960', 'Daily960'] if is_960 else ['Blitz', 'Bullet', 'Rapid', 'Daily']
    
    for mode in mode_list:
        mode_data = interval_df[interval_df['Mode'] == mode]
        if not mode_data.empty:
            # Create formatted strings with rating and win %
            mode_values = []
            for games in pivot_data['Games Played']:
                row_data = mode_data[mode_data['Games Played'] == games]
                if not row_data.empty:
                    rating = int(row_data['Average Rating'].values[0])
                    win_pct = row_data['Win %'].values[0]
                    mode_values.append(f"{rating} ({win_pct:.1f}%)")
                else:
                    mode_values.append('-')
            pivot_data[mode] = mode_values
        else:
            pivot_data[mode] = ['-'] * len(pivot_data['Games Played'])
    
    # Create column headers with total games played
    column_headers = ['Games Played']
    for mode in mode_list:
        mode_games = filtered_df[filtered_df['Mode'] == mode]
        total_games = len(mode_games)
        if total_games > 0:
            display_name = mode.replace('960', ' 960') if is_960 else mode
            column_headers.append(f'{display_name}<br>{total_games} total games')
        else:
            display_name = mode.replace('960', ' 960') if is_960 else mode
            column_headers.append(display_name)
    
    # Create plotly table
    fig = go.Figure(data=[go.Table(
        header=dict(
            values=column_headers,
            fill_color='#1e1e1e',
            font=dict(color='white', size=12),
            align='center',
            height=50
        ),
        cells=dict(
            values=[pivot_data['Games Played']] + [pivot_data.get(mode, ['-']*len(pivot_data['Games Played'])) for mode in mode_list],
            fill_color='#2d2d2d',
            font=dict(color='white', size=12),
            align='center',
            height=35
        )
    )])
    
    variant_text = 'Chess 960' if is_960 else 'Standard Chess'
    fig.update_layout(
        title=f'Average Rating (Win %) at Every {GAME_INTERVAL} Games - {variant_text}',
        template='plotly_dark',
        height=400 + (len(pivot_data['Games Played']) * 35)
    )
    
    return fig.to_html(full_html=False, include_plotlyjs='cdn')

def create_weekly_stats_table(df, is_960=False):
    """Chart 3: Weekly game statistics showing games played, win percentage, and average ELO"""
    # Filter for 960 or standard games
    filtered_df = df[df['Is960'] == is_960].copy()
    
    if filtered_df.empty:
        return "<p>No games found for this variant.</p>"
    
    # Add week column
    filtered_df['Week'] = filtered_df['Date'].dt.to_period('W').apply(lambda x: x.start_time)
    
    # Calculate stats per week and mode
    weekly_stats = []
    
    mode_list = ['Blitz960', 'Bullet960', 'Rapid960', 'Daily960'] if is_960 else ['Blitz', 'Bullet', 'Rapid', 'Daily']
    
    for week in sorted(filtered_df['Week'].unique(), reverse=True):
        week_data = filtered_df[filtered_df['Week'] == week]
        row = {'Week': week.strftime('%Y-%m-%d')}
        
        for mode in mode_list:
            mode_data = week_data[week_data['Mode'] == mode]
            if len(mode_data) > 0:
                total_games = len(mode_data)
                wins = len(mode_data[mode_data['Status'] == 'Win'])
                win_pct = (wins / total_games * 100)
                avg_elo = int(round(mode_data['Rating'].mean()))
                row[f'{mode}'] = f"{total_games} ({win_pct:.1f}%) - {avg_elo}"
            else:
                row[f'{mode}'] = "-"
        
        weekly_stats.append(row)
    
    # Create dataframe
    weekly_df = pd.DataFrame(weekly_stats)
    
    # Create plotly table
    columns = ['Week'] + mode_list
    header_labels = ['Week'] + [f'{mode.replace("960", " 960") if is_960 else mode} (Games | Win % | Avg ELO)' for mode in mode_list]
    
    fig = go.Figure(data=[go.Table(
        header=dict(
            values=header_labels,
            fill_color='#1e1e1e',
            font=dict(color='white', size=14),
            align='center',
            height=40
        ),
        cells=dict(
            values=[weekly_df[col] for col in columns],
            fill_color='#2d2d2d',
            font=dict(color='white', size=12),
            align='center',
            height=35
        )
    )])
    
    variant_text = 'Chess 960' if is_960 else 'Standard Chess'
    fig.update_layout(
        title=f'Weekly Game Statistics - {variant_text}',
        template='plotly_dark',
        height=min(600, 400 + (len(weekly_df) * 35))
    )
    
    return fig.to_html(full_html=False, include_plotlyjs='cdn')

def create_rating_boxplot(df, is_960=False):
    """Chart: Box and whisker plot showing rating distribution by game type"""
    # Filter for 960 or standard games
    filtered_df = df[df['Is960'] == is_960].copy()
    
    if filtered_df.empty:
        return "<p>No games found for this variant.</p>"
    
    # Color map for consistency
    color_map = {
        'Rapid': '#76b900', 'Blitz': '#F0C800', 
        'Bullet': '#ca3431', 'Daily': '#00BFFF',
        'Rapid960': '#76b900', 'Blitz960': '#F0C800',
        'Bullet960': '#ca3431', 'Daily960': '#00BFFF'
    }
    
    title = f'Rating Distribution by Game Type - Chess 960 (Since {START_DATE})' if is_960 else f'Rating Distribution by Game Type - Standard Chess (Since {START_DATE})'
    
    fig = go.Figure()
    
    # Get unique modes and sort them
    mode_list = ['Rapid960', 'Blitz960', 'Bullet960', 'Daily960'] if is_960 else ['Rapid', 'Blitz', 'Bullet', 'Daily']
    
    for mode in mode_list:
        mode_data = filtered_df[filtered_df['Mode'] == mode]
        if len(mode_data) > 0:
            display_name = mode.replace('960', ' 960') if is_960 else mode
            fig.add_trace(go.Box(
                y=mode_data['Rating'],
                name=display_name,
                marker_color=color_map.get(mode, '#888888'),
                boxmean='sd'  # Shows mean and standard deviation
            ))
    
    fig.update_layout(
        title=title,
        template='plotly_dark',
        yaxis_title='Rating',
        xaxis_title='Game Type',
        showlegend=False,
        height=400
    )
    
    return fig.to_html(full_html=False, include_plotlyjs='cdn')


# --- FLASK APP ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Chess.com Dashboard - {{ username }}</title>
    <style>
        body {
            background-color: #1a1a1a;
            color: #ffffff;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            color: #76b900;
            margin-bottom: 10px;
        }
        .subtitle {
            text-align: center;
            color: #888;
            margin-bottom: 40px;
        }
        .section-header {
            text-align: center;
            color: #F0C800;
            font-size: 28px;
            margin: 50px 0 30px 0;
            padding: 20px;
            background-color: #2d2d2d;
            border-radius: 10px;
            border-left: 5px solid #F0C800;
        }
        .chart-container {
            background-color: #2d2d2d;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background-color: #2d2d2d;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }
        .stat-rating {
            font-size: 24px;
            font-weight: bold;
            color: #76b900;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #444;
        }
        .stat-label {
            color: #888;
            font-size: 14px;
        }
        .rating-label {
            color: #999;
            font-size: 12px;
            margin-top: 5px;
        }
        .rapid { border-left: 4px solid #76b900; }
        .blitz { border-left: 4px solid #F0C800; }
        .bullet { border-left: 4px solid #ca3431; }
        .daily { border-left: 4px solid #00BFFF; }
        .rapid960 { border-left: 4px solid #76b900; border-right: 4px solid #9B59B6; }
        .blitz960 { border-left: 4px solid #F0C800; border-right: 4px solid #9B59B6; }
        .bullet960 { border-left: 4px solid #ca3431; border-right: 4px solid #9B59B6; }
        .daily960 { border-left: 4px solid #00BFFF; border-right: 4px solid #9B59B6; }
    </style>
</head>
<body>
    <div class="container">
        <h1>♟️ Chess.com Performance Dashboard</h1>
        <div class="subtitle">{{ username }} | Since {{ start_date }}</div>
        
        <div class="chart-container">
            <h2>📊 Overall Performance - All Game Modes</h2>
            {{ chart_overall|safe }}
        </div>
        
        <div class="section-header">♔ Standard Chess</div>
        
        <div class="stats">
            {% for mode, count in game_counts.items() %}
            {% if '960' not in mode %}
            <div class="stat-card {{ mode.lower() }}">
                <div class="stat-label">{{ mode }}</div>
                <div class="stat-value">{{ count }}</div>
                <div class="stat-label">games played</div>
                {% if mode in current_ratings %}
                <div class="stat-rating">{{ current_ratings[mode] }}</div>
                <div class="rating-label">current rating</div>
                {% endif %}
            </div>
            {% endif %}
            {% endfor %}
        </div>
        
        <div class="chart-container">
            <h2>📊 Total Games Played by Day</h2>
            {{ chart0_standard|safe }}
        </div>
        
        <div class="chart-container">
            <h2>📦 Rating Distribution by Game Type</h2>
            {{ chart4_standard|safe }}
        </div>
        
        <div class="chart-container">
            <h2>📈 Average ELO by Day</h2>
            {{ chart1_standard|safe }}
        </div>
        
        <div class="chart-container">
            <h2>📊 Average Rating Every {{ interval }} Games</h2>
            {{ chart2_standard|safe }}
        </div>
        
        <div class="chart-container">
            <h2>📅 Weekly Game Statistics</h2>
            {{ chart3_standard|safe }}
        </div>
        
        <div class="section-header">♚ Chess 960</div>
        
        <div class="stats">
            {% for mode, count in game_counts.items() %}
            {% if '960' in mode %}
            <div class="stat-card {{ mode.lower() }}">
                <div class="stat-label">{{ mode.replace('960', ' 960') }}</div>
                <div class="stat-value">{{ count }}</div>
                <div class="stat-label">games played</div>
                {% if mode in current_ratings %}
                <div class="stat-rating">{{ current_ratings[mode] }}</div>
                <div class="rating-label">current rating</div>
                {% endif %}
            </div>
            {% endif %}
            {% endfor %}
        </div>
        
        <div class="chart-container">
            <h2>📊 Total Games Played by Day</h2>
            {{ chart0_960|safe }}
        </div>
        
        <div class="chart-container">
            <h2>📦 Rating Distribution by Game Type</h2>
            {{ chart4_960|safe }}
        </div>
        
        <div class="chart-container">
            <h2>📈 Average ELO by Day</h2>
            {{ chart1_960|safe }}
        </div>
        
        <div class="chart-container">
            <h2>📊 Average Rating Every {{ interval }} Games</h2>
            {{ chart2_960|safe }}
        </div>
        
        <div class="chart-container">
            <h2>📅 Weekly Game Statistics</h2>
            {{ chart3_960|safe }}
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    print("--- FETCHING PROFILE ---")
    profile = get_data(f"https://api.chess.com/pub/player/{USERNAME}")
    
    if not profile:
        return "<h1>❌ User not found</h1>"
    
    print(f"♟️  Processing data for: {profile.get('username')}")
    
    # Fetch current ratings
    print("--- FETCHING CURRENT RATINGS ---")
    stats = get_data(f"https://api.chess.com/pub/player/{USERNAME}/stats")
    current_ratings = {}
    
    if stats:
        for mode in ['chess_rapid', 'chess_blitz', 'chess_bullet', 'chess_daily']:
            mode_name = mode.replace('chess_', '').capitalize()
            if mode in stats:
                current_ratings[mode_name] = stats[mode]['last']['rating']
        
        # Also get Chess960 ratings
        for mode in ['chess960_daily', 'chess960_rapid', 'chess960_blitz', 'chess960_bullet']:
            if mode in stats:
                base_mode = mode.replace('chess960_', '').capitalize()
                mode_name = f"{base_mode}960"
                current_ratings[mode_name] = stats[mode]['last']['rating']
    
    df = process_all_modes(USERNAME, START_DATE)
    
    if df.empty:
        return f"<h1>⚠️ No games found since {START_DATE}</h1>"
    
    # Generate game count stats
    game_counts = df['Mode'].value_counts().to_dict()
    
    # Generate overall performance chart (all modes combined)
    chart_overall = create_overall_performance_chart(df)
    
    # Generate charts for standard chess
    chart0_standard = create_daily_games_chart(df, is_960=False)
    chart1_standard = create_daily_average_chart(df, is_960=False)
    chart2_standard = create_interval_table(df, is_960=False)
    chart3_standard = create_weekly_stats_table(df, is_960=False)
    chart4_standard = create_rating_boxplot(df, is_960=False)
    
    # Generate charts for Chess 960
    chart0_960 = create_daily_games_chart(df, is_960=True)
    chart1_960 = create_daily_average_chart(df, is_960=True)
    chart2_960 = create_interval_table(df, is_960=True)
    chart3_960 = create_weekly_stats_table(df, is_960=True)
    chart4_960 = create_rating_boxplot(df, is_960=True)
    
    return render_template_string(
        HTML_TEMPLATE,
        username=profile.get('username'),
        start_date=START_DATE,
        game_counts=game_counts,
        current_ratings=current_ratings,
        interval=GAME_INTERVAL,
        chart_overall=chart_overall,
        chart0_standard=chart0_standard,
        chart1_standard=chart1_standard,
        chart2_standard=chart2_standard,
        chart3_standard=chart3_standard,
        chart4_standard=chart4_standard,
        chart0_960=chart0_960,
        chart1_960=chart1_960,
        chart2_960=chart2_960,
        chart3_960=chart3_960,
        chart4_960=chart4_960
    )

def open_browser():
    webbrowser.open('http://127.0.0.1:5000/')

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Starting Chess.com Dashboard")
    print("="*50)
    print("\n📊 Dashboard will open in your browser shortly...")
    print("🔗 URL: http://127.0.0.1:5000/")
    print("\n⚠️  Press CTRL+C to stop the server")
    print("⚠️  If browser doesn't open, manually visit: http://127.0.0.1:5000/\n")
    
    # Open browser after 2.5 seconds (longer delay for data processing)
    Timer(2.5, open_browser).start()
    
    # Run Flask app
    app.run(debug=False, port=5000, use_reloader=False)
