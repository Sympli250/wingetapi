
<?php
// Activer l'affichage des erreurs pour le débogage
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

// Configuration de l'API
$base_url = "http://localhost:4006/api";
$page = isset($_GET['page']) ? max(1, intval($_GET['page'])) : 1;
$page_size = isset($_GET['pageSize']) ? max(1, min(100, intval($_GET['pageSize']))) : 50; // Nombre de packages par page
$sort = isset($_GET['sort']) ? $_GET['sort'] : "name"; // Tri par défaut
$publisher = isset($_GET['publisher']) ? trim($_GET['publisher']) : ""; // Filtre par éditeur
$query = isset($_GET['query']) ? trim($_GET['query']) : ""; // Requête de recherche
$is_microsoft = isset($_GET['microsoft']) && $_GET['microsoft'] === '1'; // Bouton Microsoft
$refresh = isset($_GET['refresh']) && $_GET['refresh'] === '1'; // Rafraîchissement de la liste

// Si bouton Microsoft cliqué, forcer l'éditeur
if ($is_microsoft) {
    $publisher = "Microsoft";
    $query = "";
}

// Rafraîchir la liste des packages si demandé
if ($refresh) {
    $refresh_result = fetch_api("$base_url/refresh", 'POST');
    $refresh_success = isset($refresh_result['success']) && $refresh_result['success'];
    $refresh_message = $refresh_success
        ? ($refresh_result['count'] . ' packages rafraîchis avec succès !')
        : ($refresh_result['error'] ?? 'Erreur lors du rafraîchissement');
}

// Fonction pour appeler l'API avec diagnostic détaillé
function fetch_api($url, $method = 'GET', $params = []) {
    if (!function_exists('curl_init')) {
        return ['error' => "Erreur : L'extension cURL n'est pas activée dans PHP. Activez 'extension=curl' dans php.ini."];
    }

    $ch = curl_init();
    if ($method === 'GET') {
        $query_string = http_build_query($params);
        $full_url = $query_string ? "$url?$query_string" : $url;
        curl_setopt($ch, CURLOPT_URL, $full_url);
    } else {
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_POST, true);
    }
    
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 15);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false); // Localhost, pas de SSL
    curl_setopt($ch, CURLOPT_USERAGENT, 'Mozilla/5.0 (compatible; WingetPHP/1.0)');

    $response = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curl_error = curl_error($ch);
    $curl_errno = curl_errno($ch);
    
    if ($response === false || $http_code >= 400) {
        $error_msg = "Erreur cURL : $curl_error (Code: $curl_errno, HTTP: $http_code) pour $url";
        curl_close($ch);
        return ['error' => $error_msg];
    }
    
    $data = json_decode($response, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        curl_close($ch);
        return ['error' => "Erreur JSON : " . json_last_error_msg() . " pour $url"];
    }
    
    curl_close($ch);
    return $data;
}

// Déterminer l'endpoint
$endpoint = $is_microsoft ? "$base_url/packages/microsoft" : "$base_url/packages";
$params = [
    'page' => $page,
    'pageSize' => $page_size,
    'sort' => in_array($sort, ['name', 'package_id', 'version']) ? $sort : 'name'
];
if ($query && !$is_microsoft && !$publisher) {
    $params['query'] = $query;
} elseif ($publisher && !$is_microsoft) {
    $params['publisher'] = $publisher;
}

// Récupérer les données
$data = fetch_api($endpoint, 'GET', $params);
$error = isset($data['error']) ? $data['error'] : "";
$packages = $data && isset($data['Packages']) && !$error ? $data['Packages'] : [];
$total = $data && isset($data['Total']) ? $data['Total'] : 0;
$total_pages = $data && isset($data['TotalPages']) ? $data['TotalPages'] : ($total > 0 ? ceil($total / $page_size) : 1);
$current_page = $data && isset($data['CurrentPage']) ? $data['CurrentPage'] : $page;

$search_param = $publisher ? '&publisher=' . urlencode($publisher) : ($query ? '&query=' . urlencode($query) : '');
$sort_param = $sort ? '&sort=' . urlencode($sort) : '';
$microsoft_param = $is_microsoft ? '&microsoft=1' : '';
$page_size_param = '&pageSize=' . $page_size;
$refresh_link = '?refresh=1&page=1' . $search_param . $sort_param . $microsoft_param . $page_size_param;
?>
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test API Winget</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .table th, .table td { vertical-align: middle; }
    </style>
</head>
<body>
    <div class="container mt-5">
        <h1 class="mb-4">Test API Winget (localhost:4006)</h1>

        <!-- Boutons pour tester rapidement les routes de l'API -->
        <div class="mb-4">
            <h2 class="h5">Tester les routes de l'API</h2>
            <div class="btn-group" role="group">
                <a href="<?php echo $base_url; ?>/packages" target="_blank" class="btn btn-outline-primary">GET /packages</a>
                <a href="<?php echo $base_url; ?>/packages/microsoft" target="_blank" class="btn btn-outline-secondary">GET /packages/microsoft</a>
                <form method="post" action="<?php echo $base_url; ?>/refresh" target="_blank" class="d-inline">
                    <button type="submit" class="btn btn-outline-warning">POST /refresh</button>
                </form>
            </div>
        </div>

        <!-- Formulaire de recherche -->
        <form method="GET" class="mb-4">
            <div class="row g-3">
                <div class="col-md-3">
                    <input type="text" name="query" class="form-control" placeholder="Rechercher (ex. edge)..." value="<?php echo htmlspecialchars($query); ?>" <?php echo $publisher || $is_microsoft ? 'disabled' : ''; ?>>
                </div>
                <div class="col-md-3">
                    <input type="text" name="publisher" class="form-control" placeholder="Filtrer par éditeur (ex. Mozilla)..." value="<?php echo htmlspecialchars($publisher); ?>" <?php echo $is_microsoft ? 'disabled' : ''; ?>>
                </div>
                <div class="col-md-2">
                    <select name="sort" class="form-select">
                        <option value="name" <?php echo $sort === 'name' ? 'selected' : ''; ?>>Trier par Nom</option>
                        <option value="package_id" <?php echo $sort === 'package_id' ? 'selected' : ''; ?>>Trier par ID</option>
                        <option value="version" <?php echo $sort === 'version' ? 'selected' : ''; ?>>Trier par Version</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <input type="number" name="pageSize" class="form-control" min="1" max="100" value="<?php echo $page_size; ?>">
                </div>
                <div class="col-md-2">
                    <button type="submit" class="btn btn-primary w-100">Filtrer</button>
                    <a href="?page=1&pageSize=<?php echo $page_size; ?>" class="btn btn-secondary w-100 mt-2">Réinitialiser</a>
                    <a href="?page=1&publisher=Microsoft&microsoft=1&pageSize=<?php echo $page_size; ?>" class="btn btn-info w-100 mt-2">Microsoft</a>
                    <a href="<?php echo $refresh_link; ?>" class="btn btn-warning w-100 mt-2">Rafraîchir</a>
                </div>
            </div>
            <?php if ($is_microsoft): ?>
                <small class="text-muted">Filtre actif : éditeur Microsoft (<?php echo $total; ?> trouvés)</small>
            <?php elseif ($publisher): ?>
                <small class="text-muted">Filtre actif : éditeur "<?php echo htmlspecialchars($publisher); ?>" (<?php echo $total; ?> trouvés)</small>
            <?php elseif ($query): ?>
                <small class="text-muted">Recherche : "<?php echo htmlspecialchars($query); ?>" (<?php echo $total; ?> trouvés)</small>
        <?php endif; ?>
        </form>

        <?php if (isset($refresh_message)): ?>
            <div class="alert <?php echo $refresh_success ? 'alert-success' : 'alert-danger'; ?>">
                <?php echo htmlspecialchars($refresh_message); ?>
            </div>
        <?php endif; ?>

        <!-- Affichage des erreurs -->
        <?php if ($error): ?>
            <div class="alert alert-danger"><?php echo htmlspecialchars($error); ?></div>
            <p class="mt-3">Conseils de dépannage :</p>
            <ul>
                <li>Vérifiez que l'API Flask est lancée sur <code>http://localhost:4006</code>.</li>
                <li>Testez l'API : <a href="<?php echo htmlspecialchars($endpoint . ($publisher || $is_microsoft ? '' : '?' . http_build_query($params))); ?>" target="_blank">Ouvrir l'URL de l'API</a>.</li>
                <li>Consultez les logs PHP ou Flask pour plus de détails.</li>
                <li>Vérifiez cURL dans php.ini (<code>extension=curl</code>).</li>
            </ul>
        <?php elseif (empty($packages)): ?>
            <div class="alert alert-warning">Aucun package trouvé<?php echo $publisher ? ' pour l\'éditeur "' . htmlspecialchars($publisher) . '"' : ($query ? ' pour "' . htmlspecialchars($query) . '"' : ''); ?>.</div>
        <?php else: ?>
            <div class="alert alert-info">Affichage de <?php echo count($packages); ?> packages (page <?php echo $current_page; ?> sur <?php echo $total_pages; ?>).</div>
            
            <!-- Tableau des packages -->
            <div class="table-responsive">
            <table class="table table-striped table-hover align-middle">
                <thead class="table-dark">
                    <tr>
                        <th>#</th>
                        <th>Nom</th>
                        <th>Éditeur</th>
                        <th>ID</th>
                        <th>Version</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($packages as $index => $pkg): ?>
                        <tr>
                            <td><?php echo ($index + 1) + ($current_page - 1) * $page_size; ?></td>
                            <td><?php echo htmlspecialchars($pkg['name'] ?? 'N/A'); ?></td>
                            <td><?php echo htmlspecialchars($pkg['publisher'] ?? 'N/A'); ?></td>
                            <td><?php echo htmlspecialchars($pkg['package_id'] ?? 'N/A'); ?></td>
                            <td><?php echo htmlspecialchars($pkg['version'] ?? 'N/A'); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
            </div>
            
            <!-- Pagination -->
            <?php if ($total_pages > 1): ?>
                <nav aria-label="Pagination">
                    <ul class="pagination justify-content-center">
                        <li class="page-item <?php echo $current_page <= 1 ? 'disabled' : ''; ?>">
                            <a class="page-link" href="?page=<?php echo $current_page - 1 . $search_param . $sort_param . $microsoft_param . $page_size_param; ?>">Précédent</a>
                        </li>
                        <?php for ($i = max(1, $current_page - 2); $i <= min($total_pages, $current_page + 2); $i++): ?>
                            <li class="page-item <?php echo $i === $current_page ? 'active' : ''; ?>">
                                <a class="page-link" href="?page=<?php echo $i . $search_param . $sort_param . $microsoft_param . $page_size_param; ?>"><?php echo $i; ?></a>
                            </li>
                        <?php endfor; ?>
                        <li class="page-item <?php echo $current_page >= $total_pages ? 'disabled' : ''; ?>">
                            <a class="page-link" href="?page=<?php echo $current_page + 1 . $search_param . $sort_param . $microsoft_param . $page_size_param; ?>">Suivant</a>
                        </li>
                    </ul>
                </nav>
            <?php endif; ?>
        <?php endif; ?>
        
        <hr>
        <small class="text-muted">Source : API Winget locale (port 4006)</small>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
