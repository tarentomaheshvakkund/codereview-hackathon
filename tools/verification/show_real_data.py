import chromadb
import os
from services.database_service import DatabaseService
from models.database import PRAnalysis
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import json

def show_real_data():
    console = Console()
    db_path = os.environ.get('VECTOR_DB_PATH', 'chroma_db')
    
    console.print(Panel("[bold blue]Fetching Real Analyzed Data[/bold blue]"))

    # 1. ChromaDB Data
    try:
        client = chromadb.PersistentClient(path=db_path)
        collections = ['pr_analysis_knowledge', 'security_expert_knowledge', 'quality_expert_knowledge']
        
        for coll_name in collections:
            try:
                collection = client.get_collection(coll_name)
                results = collection.get(limit=2)
                
                if results and results['ids']:
                    table = Table(title=f"ChromaDB Sample: {coll_name}")
                    table.add_column("ID", style="cyan")
                    table.add_column("Title", style="green")
                    table.add_column("Issues", style="magenta")
                    table.add_column("Security", style="red")
                    
                    for i in range(len(results['ids'])):
                        meta = results['metadatas'][i]
                        table.add_row(
                            results['ids'][i],
                            str(meta.get('pr_title', 'N/A'))[:40] + "...",
                            str(meta.get('issues_found', 0)),
                            str(meta.get('security_issues', 0))
                        )
                    console.print(table)
                else:
                    console.print(f"[yellow]Collection {coll_name} is empty.[/yellow]")
            except Exception as e:
                console.print(f"[red]Error reading {coll_name}: {e}[/red]")
    except Exception as e:
        console.print(f"[red]ChromaDB Error: {e}[/red]")

    # 2. PostgreSQL Data
    try:
        db_service = DatabaseService()
        with db_service.get_session() as session:
            prs = session.query(PRAnalysis).order_by(PRAnalysis.analyzed_at.desc()).limit(3).all()
            
            if prs:
                table = Table(title="PostgreSQL Sample: PR Analysis Results")
                table.add_column("PR #", style="cyan")
                table.add_column("Repo", style="blue")
                table.add_column("Quality Score", style="green")
                table.add_column("Analyzed At", style="magenta")
                
                for pr in prs:
                    table.add_row(
                        str(pr.pr_number),
                        pr.repository,
                        f"{pr.overall_quality_score:.2f}" if pr.overall_quality_score else "N/A",
                        pr.analyzed_at.strftime("%Y-%m-%d %H:%M:%S") if pr.analyzed_at else "N/A"
                    )
                console.print(table)
            else:
                console.print("[yellow]PostgreSQL table pr_analysis is empty.[/yellow]")
    except Exception as e:
        console.print(f"[red]PostgreSQL Error: {e}[/red]")

if __name__ == "__main__":
    show_real_data()
