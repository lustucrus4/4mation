"""
Script de test pour OptimizedMinimaxAdvisor
"""

import numpy as np
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from game.game_engine import GameEngine
import time

def test_basic_functionality():
    """Test basique de fonctionnement"""
    print("=" * 60)
    print("Test 1: Fonctionnalité de base")
    print("=" * 60)
    
    advisor = OptimizedMinimaxAdvisor(depth=4, use_iterative_deepening=False)
    
    # Créer un plateau de test
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1  # Premier coup au centre
    board[3, 4] = 2   # Réponse
    
    print(f"Plateau de test:")
    print(board)
    print(f"\nJoueur actuel: 1")
    
    start_time = time.time()
    analysis = advisor.analyze_position(board, current_player=1, last_move=(3, 4))
    elapsed = time.time() - start_time
    
    print(f"\n[OK] Analyse terminee en {elapsed:.2f}s")
    print(f"   Coups valides: {analysis['valid_moves_count']}")
    print(f"   Meilleur coup: {analysis['best_move']}")
    
    if analysis['moves']:
        print(f"\nTop 5 coups:")
        for i, move_info in enumerate(analysis['moves'][:5], 1):
            print(f"   {i}. ({move_info['row']}, {move_info['col']}): "
                  f"{move_info['win_probability']*100:.1f}% "
                  f"(score: {move_info['score']:.3f})")
    
    stats = advisor.get_cache_stats()
    print(f"\n[STATS] Statistiques du cache:")
    print(f"   Hits: {stats['hits']}, Misses: {stats['misses']}")
    print(f"   Taux de hit: {stats['hit_rate']:.1f}%")
    print(f"   Taille: {stats['size']}/{stats['max_size']}")
    print(f"   Nœuds explorés: {stats['nodes_searched']}")
    print(f"   Nœuds quiescence: {stats['quiescence_nodes']}")


def test_performance_comparison():
    """Compare les performances avec différentes profondeurs"""
    print("\n" + "=" * 60)
    print("Test 2: Comparaison de performance")
    print("=" * 60)
    
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    board[3, 4] = 2
    board[2, 3] = 1
    board[2, 4] = 2
    
    print(f"Plateau de test (4 coups joués):")
    print(board)
    
    depths = [4, 6, 8]
    for depth in depths:
        print(f"\n--- Profondeur {depth} ---")
        advisor = OptimizedMinimaxAdvisor(depth=depth, use_iterative_deepening=False)
        
        start_time = time.time()
        analysis = advisor.analyze_position(board, current_player=1, last_move=(2, 4))
        elapsed = time.time() - start_time
        
        stats = advisor.get_cache_stats()
        print(f"Temps: {elapsed:.2f}s")
        print(f"Nœuds: {stats['nodes_searched']}")
        print(f"Cache hit rate: {stats['hit_rate']:.1f}%")
        if analysis['best_move']:
            print(f"Meilleur coup: {analysis['best_move']}")


def test_iterative_deepening():
    """Test de l'iterative deepening"""
    print("\n" + "=" * 60)
    print("Test 3: Iterative Deepening")
    print("=" * 60)
    
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    board[3, 4] = 2
    
    print("Sans iterative deepening:")
    advisor1 = OptimizedMinimaxAdvisor(depth=6, use_iterative_deepening=False)
    start = time.time()
    analysis1 = advisor1.analyze_position(board, current_player=1, last_move=(3, 4))
    time1 = time.time() - start
    stats1 = advisor1.get_cache_stats()
    print(f"  Temps: {time1:.2f}s, Nœuds: {stats1['nodes_searched']}")
    
    print("\nAvec iterative deepening:")
    advisor2 = OptimizedMinimaxAdvisor(depth=6, use_iterative_deepening=True)
    start = time.time()
    analysis2 = advisor2.analyze_position(board, current_player=1, last_move=(3, 4))
    time2 = time.time() - start
    stats2 = advisor2.get_cache_stats()
    print(f"  Temps: {time2:.2f}s, Nœuds: {stats2['nodes_searched']}")
    
    if analysis1['best_move'] == analysis2['best_move']:
        print(f"\n[OK] Meme meilleur coup: {analysis1['best_move']}")
    else:
        print(f"\n[WARNING] Coups differents:")
        print(f"   Sans ID: {analysis1['best_move']}")
        print(f"   Avec ID: {analysis2['best_move']}")


def test_move_ordering():
    """Test de l'ordre des coups"""
    print("\n" + "=" * 60)
    print("Test 4: Ordre des coups")
    print("=" * 60)
    
    # Créer une position avec une menace
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    board[3, 4] = 1
    board[3, 5] = 1  # 3 alignés pour le joueur 1
    
    advisor = OptimizedMinimaxAdvisor(depth=4)
    moves = advisor._get_frontier_moves(board, (3, 5), 1)
    ordered = advisor._order_moves(board, moves, 1, (3, 5))
    
    print(f"Coups valides: {len(moves)}")
    print(f"\nOrdre des coups (top 5):")
    for i, move in enumerate(ordered[:5], 1):
        is_win = advisor._is_winning_move(board, move, 1)
        is_block = advisor._is_blocking_move(board, move, 1)
        threats = advisor._count_threats(board, move, 1)
        print(f"   {i}. {move}: win={is_win}, block={is_block}, threats={threats}")


def test_cache_effectiveness():
    """Test de l'efficacité du cache"""
    print("\n" + "=" * 60)
    print("Test 5: Efficacité du cache")
    print("=" * 60)
    
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    board[3, 4] = 2
    
    advisor = OptimizedMinimaxAdvisor(depth=6)
    
    # Première analyse
    print("Première analyse...")
    start = time.time()
    analysis1 = advisor.analyze_position(board, current_player=1, last_move=(3, 4))
    time1 = time.time() - start
    stats1 = advisor.get_cache_stats()
    print(f"  Temps: {time1:.2f}s")
    print(f"  Cache: {stats1['hits']} hits, {stats1['misses']} misses")
    
    # Deuxième analyse (même position, devrait utiliser le cache)
    print("\nDeuxième analyse (même position)...")
    start = time.time()
    analysis2 = advisor.analyze_position(board, current_player=1, last_move=(3, 4))
    time2 = time.time() - start
    stats2 = advisor.get_cache_stats()
    print(f"  Temps: {time2:.2f}s")
    print(f"  Cache: {stats2['hits']} hits, {stats2['misses']} misses")
    print(f"  Amélioration: {((time1 - time2) / time1 * 100):.1f}% plus rapide")


def test_winning_scenarios():
    """Test des scénarios gagnants"""
    print("\n" + "=" * 60)
    print("Test 6: Scénarios gagnants")
    print("=" * 60)
    
    advisor = OptimizedMinimaxAdvisor(depth=6)
    
    # Position avec coup gagnant
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    board[3, 4] = 1
    board[3, 5] = 1  # 3 alignés
    
    print("Position avec 3 alignés (coup gagnant disponible):")
    print(board)
    
    analysis = advisor.analyze_position(board, current_player=1, last_move=(3, 5))
    
    if analysis['best_move']:
        is_win = advisor._is_winning_move(board, analysis['best_move'], 1)
        print(f"\nMeilleur coup: {analysis['best_move']}")
        print(f"Est-ce un coup gagnant? {is_win}")
        
        if is_win:
            print("[OK] L'IA trouve le coup gagnant!")
        else:
            print("[WARNING] L'IA n'a pas trouve le coup gagnant")


def test_tactical_win():
    """Test victoire en 1 détectée avant Minimax"""
    print("\n" + "=" * 60)
    print("Test 7: Victoire tactique en 1")
    print("=" * 60)

    advisor = OptimizedMinimaxAdvisor(depth=4, use_iterative_deepening=False)
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    board[3, 4] = 1
    board[3, 5] = 1

    analysis = advisor.analyze_position(board, current_player=1, last_move=(3, 5))
    assert analysis.get("tactical") is True
    assert analysis["best_move"] == (3, 6), f"Victoire attendue (3,6), obtenu {analysis['best_move']}"
    print(f"[OK] Coup gagnant trouvé: {analysis['best_move']}")


def test_tactical_block():
    """Test blocage obligatoire respectant l'adjacence au last_move"""
    print("\n" + "=" * 60)
    print("Test 8: Blocage tactique obligatoire")
    print("=" * 60)

    advisor = OptimizedMinimaxAdvisor(depth=4, use_iterative_deepening=False)
    board = np.zeros((7, 7), dtype=np.int8)
    # Joueur 1 menace victoire en (3,3) — trois alignés cols 0-2
    board[3, 0] = 1
    board[3, 1] = 1
    board[3, 2] = 1
    # Dernier coup joueur 1 en (3,2) — joueur 2 doit bloquer en (3,3)
    last_move = (3, 2)

    valid = advisor._get_frontier_moves(board, last_move, current_player=2)
    assert (3, 3) in valid, f"(3,3) doit être légal, coups={valid}"

    analysis = advisor.analyze_position(board, current_player=2, last_move=last_move)
    assert analysis.get("tactical") is True
    assert analysis["best_move"] == (3, 3), f"Bloc attendu (3,3), obtenu {analysis['best_move']}"
    print(f"[OK] Blocage obligatoire: {analysis['best_move']}")


def test_evaluate_move_last_move():
    """Test que evaluate_move utilise last_move pour la légalité"""
    print("\n" + "=" * 60)
    print("Test 9: evaluate_move et last_move")
    print("=" * 60)

    advisor = OptimizedMinimaxAdvisor(depth=3, use_iterative_deepening=False)
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    board[3, 4] = 2
    last_move = (3, 4)

    # (0,0) n'est pas adjacent — doit être rejeté
    score_invalid = advisor.evaluate_move(board, (0, 0), 1, last_move=last_move)
    assert score_invalid == -1.0, "Coup non adjacent doit scorer -1"

    # (2,4) est adjacent au last_move
    score_valid = advisor.evaluate_move(board, (2, 4), 1, last_move=last_move)
    assert score_valid > -1.0, "Coup légal ne doit pas scorer -1"
    print(f"[OK] Coup illégal=-1.0, coup légal={score_valid:.3f}")


def main():
    """Lance tous les tests"""
    print("\n" + "=" * 60)
    print("TESTS DU MODÈLE MINIMAX OPTIMISÉ")
    print("=" * 60)
    
    try:
        test_basic_functionality()
        test_performance_comparison()
        test_iterative_deepening()
        test_move_ordering()
        test_cache_effectiveness()
        test_winning_scenarios()
        test_tactical_win()
        test_tactical_block()
        test_evaluate_move_last_move()
        
        print("\n" + "=" * 60)
        print("[OK] Tous les tests termines!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERREUR] Erreur pendant les tests: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

